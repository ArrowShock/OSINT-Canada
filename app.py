import streamlit as st
import os
from urllib.parse import urlparse, unquote, quote
import pandas as pd
import webbrowser

st.set_page_config(page_title="OSINT 下载器 (V27 最终版)", layout="wide", page_icon="🕵️")

# --- 核心辅助函数 ---
def is_target_file(href):
    valid = ['.pdf', '.xlsx', '.xls', '.csv', '.docx', '.doc', '.zip']
    return any(href.lower().endswith(ext) for ext in valid)

def safe_encode_url(url):
    parts = urlparse(url)
    safe_path = quote(parts.path) 
    new_url = parts.scheme + "://" + parts.netloc + safe_path
    if parts.query: new_url += "?" + parts.query
    return new_url

def generate_html_downloader(file_list):
    """生成本地下载控制台 HTML"""
    # 这里生成一段 JavaScript，让浏览器自己去下载，从而继承所有 Cookie 和验证状态
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>DOJ 批量下载控制台</title>
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; padding: 40px; background-color: #f5f7fa; }}
            .card {{ max-width: 900px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 20px; margin-top: 0; }}
            .alert {{ background: #e8f0fe; color: #174ea6; padding: 15px; border-radius: 8px; margin-bottom: 30px; border-left: 5px solid #174ea6; }}
            .btn-main {{ 
                background-color: #d93025; color: white; border: none; padding: 12px 24px; 
                font-size: 16px; font-weight: bold; border-radius: 6px; cursor: pointer; 
                transition: background 0.2s; display: inline-block; text-decoration: none;
            }}
            .btn-main:hover {{ background-color: #b31412; }}
            .file-list {{ border: 1px solid #eee; border-radius: 8px; overflow: hidden; }}
            .file-item {{ 
                padding: 12px 20px; border-bottom: 1px solid #eee; display: flex; 
                justify-content: space-between; align-items: center; background: #fff;
            }}
            .file-item:last-child {{ border-bottom: none; }}
            .file-item:hover {{ background-color: #f8f9fa; }}
            .status {{ font-size: 14px; color: #666; font-weight: bold; }}
            .status.done {{ color: #28a745; }}
        </style>
        <script>
            async function downloadAll() {{
                const links = document.querySelectorAll('a.download-link');
                const btn = document.getElementById('main-btn');
                btn.innerText = "⏳ 正在请求浏览器下载...";
                btn.disabled = true;
                btn.style.backgroundColor = "#ccc";

                let count = 0;
                for (const link of links) {{
                    link.click(); // 触发点击
                    count++;
                    // 标记状态
                    const statusSpan = document.getElementById('status-' + count);
                    if(statusSpan) {{
                        statusSpan.innerText = "✅ 已发送请求";
                        statusSpan.classList.add('done');
                    }}
                    // 间隔 1.2 秒，防止浏览器卡死
                    await new Promise(r => setTimeout(r, 1200));
                }}
                
                alert("已全部发送请求！\\n请检查浏览器的下载管理器。\\n如果有弹窗询问'是否允许下载多个文件'，请务必点【允许】。");
                btn.innerText = "✅ 完成";
            }}
        </script>
    </head>
    <body>
        <div class="card">
            <h1>📂 准备下载 {len(file_list)} 个文件</h1>
            
            <div class="alert">
                <strong>关键步骤：</strong> 此页面必须在 <u>通过了 18+ 验证</u> 的浏览器中打开。<br>
                点击下方按钮后，如果浏览器拦截弹窗，请留意地址栏右侧的小图标，选择 <strong>“始终允许”</strong>。
            </div>

            <div style="text-align: center; margin-bottom: 30px;">
                <button id="main-btn" onclick="downloadAll()" class="btn-main">⚡ 开始批量下载全部</button>
            </div>

            <div class="file-list">
    """
    
    idx = 0
    for f in file_list:
        idx += 1
        clean_url = safe_encode_url(f['URL'])
        html_content += f"""
                <div class="file-item">
                    <span style="font-family: monospace;">{idx}. {f['文件名']}</span>
                    <div>
                        <span id="status-{idx}" class="status">等待中</span>
                        <a href="{clean_url}" class="download-link" download target="_blank" style="display:none;"></a>
                    </div>
                </div>
        """
    
    html_content += """
            </div>
        </div>
    </body>
    </html>
    """
    
    filename = "DOJ_Downloader.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    return filename

# --- 主界面 ---
st.title("🕵️ OSINT 下载器 (V27 最终版)")
st.warning("⚠️ 重要提示：请勿在目标网站按 F12，这会导致会话重置！请使用 Link Gopher 提取链接。")

if 'found_files' not in st.session_state: st.session_state['found_files'] = []

# 输入区
st.info("请将 Link Gopher 提取的链接粘贴到下方 (无视乱码和空格，App 会自动处理)：")
raw_text = st.text_area("链接粘贴区", height=200, placeholder="https://www.justice.gov/...\nhttps://www.justice.gov/...")

if st.button("🔍 1. 解析链接"):
    if raw_text:
        lines = raw_text.splitlines()
        files = []
        seen = set()
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # 只要包含 http 和 pdf 就提取
            if "http" in line and is_target_file(line):
                # 粗暴提取：从 http 开始截取
                http_pos = line.find("http")
                clean_url = line[http_pos:]
                
                # 再次清理可能粘连的后缀
                # 比如 ...pdf - Dataset 10 -> ...pdf
                # 简单逻辑：找到 .pdf 的位置，向后截取 4 位
                ext_pos = clean_url.lower().find(".pdf")
                if ext_pos != -1:
                    clean_url = clean_url[:ext_pos+4]
                
                if clean_url not in seen:
                    try:
                        name = os.path.basename(unquote(urlparse(clean_url).path))
                    except: name = "doc.pdf"
                    
                    files.append({"序号": len(files)+1, "文件名": name, "URL": clean_url})
                    seen.add(clean_url)
        
        st.session_state['found_files'] = files
        if files:
            st.success(f"成功识别 {len(files)} 个 PDF 文件！")
        else:
            st.error("未找到有效链接，请检查粘贴内容。")

# 生成区
if st.session_state['found_files']:
    st.markdown("---")
    df = pd.DataFrame(st.session_state['found_files'])
    st.dataframe(df, hide_index=True, use_container_width=True)
    
    if st.button(f"🔥 2. 生成下载控制台 (共 {len(st.session_state['found_files'])} 个文件)", type="primary"):
        # 生成 HTML
        file_path = generate_html_downloader(st.session_state['found_files'])
        abs_path = os.path.abspath(file_path)
        
        st.markdown(f"""
        ### ✅ 准备就绪！
        
        我们已经为您生成了一个本地网页： **`DOJ_Downloader.html`**
        
        **请执行以下最后一步：**
        1. 打开您的文件夹，找到这个文件。
        2. **双击它** (它会在 Chrome/Edge 中打开)。
        3. 那个浏览器应该正好是您**已经通过了 18+ 验证**的那个。
        4. 点击页面中间的红色大按钮 **“⚡ 开始批量下载全部”**。
        
        *(文件路径: `{abs_path}`)*
        """)
        
        # 尝试自动打开文件夹
        try: os.startfile(os.path.dirname(abs_path))
        except: pass
