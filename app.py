import streamlit as st
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin, urlparse, unquote
import io
import zipfile
import urllib3
import time
import pandas as pd

# --- 🤫 屏蔽 SSL 警告 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 页面配置 ---
st.set_page_config(page_title="OSINT 云端批量下载器", layout="wide", page_icon="🕵️")

# --- 🎨 CSS 终极美化 (紧凑版) ---
st.markdown("""
    <style>
    /* 1. 顶部留白切除术：大幅减少页面顶部的空白 */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 1rem !important;
    }
    
    /* 2. 标题与Tag优化 */
    h1 {
        margin-bottom: 0.5rem !important;
    }
    
    /* 3. 自定义分割线 (替代占地方的 ---) */
    .compact-divider {
        border-top: 1px solid #e6e6e6;
        margin-top: 10px;
        margin-bottom: 15px;
    }
    
    /* 4. 统一 Step 标题样式 */
    .step-header {
        font-size: 22px;
        font-weight: 700;
        color: #0f52ba; /* 专业的科技蓝 */
        margin-bottom: 10px;
        display: flex;
        align-items: center;
    }
    
    /* 5. 按钮样式微调 */
    .stButton>button { 
        width: 100%; 
        border-radius: 8px;
        font-weight: bold;
    }
    
    /* Feature Tag 样式 */
    .feature-tag { 
        display: inline-block; padding: 3px 10px; border-radius: 15px; 
        background-color: #f0f2f6; color: #444; font-size: 0.8em; 
        margin-right: 6px; border: 1px solid #ddd;
    }
    </style>
""", unsafe_allow_html=True)

# --- 辅助函数 ---
def get_ext(filename):
    base, ext = os.path.splitext(filename)
    if not ext: return ".unknown"
    return ext.lower()

def is_target_file(href):
    valid_exts = ['.pdf', '.xlsx', '.xls', '.csv', '.docx', '.doc', '.zip', '.json', '.xml', '.txt', '.png', '.jpg']
    return any(href.lower().endswith(ext) for ext in valid_exts) or 'download' in href.lower()

# --- 主界面 ---

# 1. 标题区
st.title("🕵️ OSINT 云端批量下载器")

# Feature Highlights
st.markdown("""
    <div style="margin-bottom: 10px;">
        <span class="feature-tag">✨ 无需安装 Python</span>
        <span class="feature-tag">📂 支持多种格式</span>
        <span class="feature-tag">🔢 ID 智能区间选择</span>
        <span class="feature-tag">🚀 专为 OSINT 设计</span>
    </div>
    <div class="compact-divider"></div> 
""", unsafe_allow_html=True) # 使用自定义紧凑分割线

# 初始化 Session State
if 'found_files' not in st.session_state: st.session_state['found_files'] = []

# --- Step 1 区块 ---
# 使用 Markdown 模拟统一的标题样式
st.markdown('<div class="step-header">Step 1. 扫描文件列表</div>', unsafe_allow_html=True)

col_input, col_btn = st.columns([3, 1])
with col_input:
    target_url = st.text_input("URL", placeholder="在此粘贴目标网址 (例如 https://...)", label_visibility="collapsed")
with col_btn:
    # 按钮文字现在只负责动作，不负责显示步骤，看起来更清爽
    start_scan = st.button("🚀 开始扫描", use_container_width=True)

if start_scan:
    if not target_url:
        st.warning("请先输入网址！")
    else:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            with st.spinner("正在云端扫描..."):
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
                        if '.' not in raw_name[-5:]: 
                            if 'pdf' in href.lower(): raw_name += '.pdf'
                            else: raw_name += '.html'
                        
                        link_text = a_tag.get_text(strip=True)
                        display_name = link_text if len(link_text) > 3 else raw_name
                        
                        files.append({
                            "下载?": False,
                            "序号": len(files) + 1,
                            "文件名": display_name,
                            "类型": get_ext(raw_name).upper().replace(".", ""),
                            "原始文件名": raw_name,
                            "URL": full_url
                        })
                
                st.session_state['found_files'] = files
                st.toast(f"扫描完成！发现 {len(files)} 个文件。", icon="✅")
                
        except Exception as e:
            st.error(f"扫描失败: {e}")

# --- Step 2 区块 ---
if st.session_state['found_files']:
    # 再次使用紧凑分割线
    st.markdown('<div class="compact-divider"></div>', unsafe_allow_html=True)
    
    # Step 2 标题，与 Step 1 保持严格一致
    st.markdown('<div class="step-header">Step 2. 选择与下载</div>', unsafe_allow_html=True)
    
    # === 智能选择器 ===
    with st.container():
        c1, c2, c3, c4 = st.columns([1, 1, 1.5, 3])
        with c1:
            start_id = st.number_input("起始 ID", min_value=1, value=1)
        with c2:
            end_id = st.number_input("结束 ID", min_value=1, value=min(len(st.session_state['found_files']), 20))
        with c3:
            st.write("") 
            st.write("")
            if st.button("✅ 勾选此范围"):
                for f in st.session_state['found_files']:
                    if start_id <= f['序号'] <= end_id:
                        f['下载?'] = True
                st.toast(f"已勾选 {start_id}-{end_id}", icon="⚡")

        with c4:
             st.write("")
             st.write("")
             if st.button("🗑️ 清空所有"):
                 for f in st.session_state['found_files']:
                     f['下载?'] = False
                 st.rerun()

    # === 表格 ===
    df = pd.DataFrame(st.session_state['found_files'])
    
    edited_df = st.data_editor(
        df,
        column_config={
            "下载?": st.column_config.CheckboxColumn("选?", width="small"),
            "序号": st.column_config.NumberColumn("No.", width="small", format="%d"),
            "URL": st.column_config.LinkColumn("链接"),
        },
        disabled=["序号", "文件名", "类型", "原始文件名", "URL"],
        hide_index=True,
        use_container_width=True,
        height=400,
        key="editor"
    )
    
    selected_rows = edited_df[edited_df["下载?"] == True]
    count = len(selected_rows)
    
    st.info(f"当前选中: {count} 个文件")

    # 下载按钮
    if st.button(f"📦 开始打包下载 ({count} 个文件)", type="primary"):
        if count == 0:
            st.warning("⚠️ 请至少勾选一个文件！")
        else:
            zip_buffer = io.BytesIO()
            headers = {"User-Agent": "Mozilla/5.0"}
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            download_list = selected_rows.to_dict('records')
            total = len(download_list)
            success_count = 0
            
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for i, item in enumerate(download_list):
                    try:
                        status_text.text(f"正在下载... ({i+1}/{total}) {item['原始文件名']}")
                        r = requests.get(item['URL'], headers=headers, verify=False, timeout=60)
                        zf.writestr(item['原始文件名'], r.content)
                        success_count += 1
                        time.sleep(1)
                    except:
                        pass
                    progress_bar.progress((i + 1) / total)
            
            status_text.empty()
            progress_bar.empty()
            
            st.download_button(
                label=f"🚀 下载 ZIP 包 ({success_count} 个文件)",
                data=zip_buffer.getvalue(),
                file_name=f"OSINT_Files_{int(time.time())}.zip",
                mime="application/zip",
                type="primary"
            )
