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

# --- CSS 美化 ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; min-height: 50px; font-size: 16px; font-weight: 600; }
    .feature-tag { 
        display: inline-block; 
        padding: 4px 12px; 
        border-radius: 20px; 
        background-color: #f0f2f6; 
        color: #31333F; 
        font-size: 0.85em; 
        margin-right: 8px; 
        margin-bottom: 8px;
        border: 1px solid #d6d6d8;
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
st.title("🕵️ OSINT 云端批量下载器")

# 功能 Highlights
st.markdown("""
    <span class="feature-tag">✨ 无需安装 Python</span>
    <span class="feature-tag">📂 支持 PDF/Excel/Word 等多种格式</span>
    <span class="feature-tag">📊 表格级筛选 & 排序</span>
    <span class="feature-tag">🚀 专为 OSINT 长期追踪设计</span>
""", unsafe_allow_html=True)

st.caption("输入网址 -> 智能扫描 -> 像 Excel 一样勾选需要的文件 (支持增量下载) -> 一键打包")
st.markdown("---")

target_url = st.text_input("🔗 输入目标网址:", placeholder="https://...")

# 初始化 Session State
if 'found_files' not in st.session_state: st.session_state['found_files'] = []
if 'select_all' not in st.session_state: st.session_state['select_all'] = False 

# --- 1. 扫描逻辑 ---
if st.button("🔍 1. 扫描文件列表"):
    if not target_url:
        st.warning("请先输入网址！")
    else:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
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
                            "下载?": False, # 默认初始状态
                            "文件名": display_name,
                            "类型": get_ext(raw_name).upper().replace(".", ""),
                            "原始文件名": raw_name,
                            "URL": full_url
                        })
                
                st.session_state['found_files'] = files
                st.session_state['select_all'] = False # 重置全选状态
                st.success(f"扫描完成！发现 {len(files)} 个文件。")
                
        except Exception as e:
            st.error(f"扫描失败: {e}")

# --- 2. 表格操作区 ---
if st.session_state['found_files']:
    st.markdown("---")
    st.subheader("2️⃣ 选择与下载")
    
    # 转换数据为 DataFrame
    df = pd.DataFrame(st.session_state['found_files'])
    
    # --- 全选/全不选 按钮逻辑 ---
    col_btn, col_info = st.columns([1, 4])
    with col_btn:
        # 这是一个切换按钮
        if st.button("✅ 全选 / ⬜ 全不选"):
            st.session_state['select_all'] = not st.session_state['select_all']
    
    # 根据按钮状态，强制更新 DataFrame 的勾选状态
    if st.session_state['select_all']:
        df["下载?"] = True
    else:
        # 注意：这里我们不强制设为 False，否则用户手动勾选的会被冲掉
        # 只有在刚点击“全不选”的那一瞬间可能需要重置，但在 Streamlit 里
        # 最简单的逻辑是：如果用户想全选，点按钮；如果想微调，直接在表格里点。
        # 为了方便，这里设定：点击按钮 -> 变为全选；再点 -> 变为全选取消（回到初始表格）
        pass

    # 如果是“全选”模式，覆盖数据；否则使用 data_editor 的默认编辑能力
    if st.session_state['select_all']:
        df["下载?"] = True
        
    # 显示表格
    edited_df = st.data_editor(
        df,
        column_config={
            "下载?": st.column_config.CheckboxColumn("下载?", width="small"),
            "URL": st.column_config.LinkColumn("链接"),
        },
        disabled=["文件名", "类型", "原始文件名", "URL"],
        hide_index=True,
        use_container_width=True,
        height=400,
        key="editor" # 赋予唯一 key
    )
    
    # 统计选中项
    selected_rows = edited_df[edited_df["下载?"] == True]
    count = len(selected_rows)
    
    with col_info:
        if st.session_state['select_all']:
            st.info(f"⚡ 已启用全选模式。当前选中: {count} 个文件")
        else:
            st.info(f"当前选中: {count} 个文件 (点击左侧按钮可一键全选)")

    # 3. 下载按钮
    if st.button(f"📦 开始打包下载 ({count} 个文件)"):
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
                        status_text.text(f"正在下载 ({i+1}/{total}): {item['原始文件名']}...")
                        r = requests.get(item['URL'], headers=headers, verify=False, timeout=60)
                        zf.writestr(item['原始文件名'], r.content)
                        success_count += 1
                        time.sleep(1)
                    except:
                        pass
                    progress_bar.progress((i + 1) / total)
            
            status_text.text("✅ 打包完成！")
            progress_bar.empty()
            
            st.download_button(
                label=f"🚀 下载 ZIP 包 ({success_count} 个文件)",
                data=zip_buffer.getvalue(),
                file_name="OSINT_Files.zip",
                mime="application/zip",
                type="primary"
            )
