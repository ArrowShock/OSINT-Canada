import streamlit as st
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin, urlparse, unquote
import io
import zipfile
import urllib3
import time

# --- 🤫 屏蔽 SSL 警告 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 页面配置 ---
st.set_page_config(page_title="OSINT 云端下载器", layout="wide", page_icon="🕵️")

# --- CSS 美化 ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; min-height: 60px; font-size: 18px; font-weight: 700; }
    .success-log { color: #0f5132; background-color: #d1e7dd; padding: 6px; border-radius: 4px; border-left: 4px solid #198754; margin-bottom: 2px; }
    .badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; color: white; margin-right: 8px; font-weight: bold; min-width: 40px; text-align: center;}
    .pdf-bg { background-color: #b30b00; }
    .xls-bg { background-color: #1d6f42; }
    .doc-bg { background-color: #2b579a; }
    .zip-bg { background-color: #e6a200; color: black; }
    .other-bg { background-color: #6c757d; }
    </style>
""", unsafe_allow_html=True)

# --- 辅助函数 ---
def get_ext(filename):
    """获取标准化的后缀名 (带点, 小写)"""
    base, ext = os.path.splitext(filename)
    if not ext: return ".unknown"
    return ext.lower()

def get_file_type_badge(filename):
    ext = get_ext(filename)
    if ext == '.pdf': return "<span class='badge pdf-bg'>PDF</span>"
    if ext in ['.xlsx', '.xls', '.csv']: return "<span class='badge xls-bg'>XLS</span>"
    if ext in ['.docx', '.doc']: return "<span class='badge doc-bg'>DOC</span>"
    if ext in ['.zip', '.rar']: return "<span class='badge zip-bg'>ZIP</span>"
    return f"<span class='badge other-bg'>{ext.replace('.', '').upper()}</span>"

def is_target_file(href):
    # 放宽入口标准，让过滤器来决定要不要
    valid_exts = ['.pdf', '.xlsx', '.xls', '.csv', '.docx', '.doc', '.zip', '.json', '.xml', '.txt', '.png', '.jpg']
    return any(href.lower().endswith(ext) for ext in valid_exts) or 'download' in href.lower()

# --- 主界面 ---
st.title("🕵️ OSINT 云端批量下载器 (精准过滤版)")
st.caption("支持 KSV / Deloitte / FTI 等 | 自动去重 | 按类型筛选")
st.markdown("---")

target_url = st.text_input("🔗 输入目标网址:", placeholder="https://...")

if 'found_files' not in st.session_state: st.session_state['found_files'] = []

# --- 1. 扫描 ---
if st.button("🔍 1. 扫描文件列表"):
    if not target_url:
        st.warning("请先输入网址！")
    else:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            with st.spinner("正在扫描..."):
                response = requests.get(target_url, headers=headers, verify=False)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                files = []
                seen_urls = set()
                
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']
                    full_url = urljoin(target_url, href)
                    if full_url in seen_urls: continue
                    
                    if is_target_file(href):
                        seen_urls.add(full_url)
                        raw_name = os.path.basename(unquote(urlparse(full_url).path))
                        # 如果没有后缀，尝试根据href猜测
                        if '.' not in raw_name[-5:]: 
                            if 'pdf' in href.lower(): raw_name += '.pdf'
                            else: raw_name += '.html' # 假设是网页链接
                            
                        link_text = a_tag.get_text(strip=True)
                        display_name = link_text if len(link_text) > 3 else raw_name
                        files.append({"name": display_name, "url": full_url, "file": raw_name})
                
                st.session_state['found_files'] = files
                st.success(f"扫描完成！发现 {len(files)} 个链接。")
                
        except Exception as e:
            st.error(f"扫描失败: {e}")

# --- 2. 筛选与下载 ---
if st.session_state['found_files']:
    st.markdown("---")
    st.subheader("2️⃣ 筛选与下载")
    
    # 1. 提取所有出现的后缀名
    all_extensions = sorted(list(set([get_ext(f['file']) for f in st.session_state['found_files']])))
    
    # 2. 让用户选择 (默认全选)
    selected_exts = st.multiselect(
        "📂 请选择要下载的文件类型 (可多选):",
        options=all_extensions,
        default=all_extensions
    )
    
    # 3. 根据选择过滤文件列表
    filtered_files = [f for f in st.session_state['found_files'] if get_ext(f['file']) in selected_exts]
    
    st.info(f"已选中 {len(filtered_files)} 个文件 (共发现 {len(st.session_state['found_files'])})")
    
    # 4. 预览列表 (只显示选中的)
    with st.expander("点击查看选中文件列表"):
        for item in filtered_files:
            badge = get_file_type_badge(item['file'])
            st.markdown(f"<div>{badge} {item['name']}</div>", unsafe_allow_html=True)

    # 5. 下载按钮
    if st.button(f"📦 打包下载选中的 {len(filtered_files)} 个文件"):
        if len(filtered_files) == 0:
            st.warning("您没有选择任何文件！")
        else:
            zip_buffer = io.BytesIO()
            headers = {"User-Agent": "Mozilla/5.0"}
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                total = len(filtered_files)
                success_count = 0
                
                for i, item in enumerate(filtered_files):
                    try:
                        status_text.text(f"正在下载 ({i+1}/{total}): {item['file']}...")
                        r = requests.get(item['url'], headers=headers, verify=False, timeout=30)
                        zf.writestr(item['file'], r.content)
                        success_count += 1
                        time.sleep(1) # 保持礼貌
                    except:
                        pass
                    progress_bar.progress((i + 1) / total)
            
            status_text.text("打包完成！")
            progress_bar.empty()
            
            st.download_button(
                label=f"🚀 点击下载 ZIP ({success_count} 个文件)",
                data=zip_buffer.getvalue(),
                file_name="OSINT_Filtered_Files.zip",
                mime="application/zip",
                type="primary"
            )
