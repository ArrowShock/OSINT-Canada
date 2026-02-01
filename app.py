import streamlit as st
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin, urlparse, unquote, quote
import io
import zipfile
import urllib3
import time
import pandas as pd

# 屏蔽警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="OSINT 下载器 (V23 修复版)", layout="wide", page_icon="🕵️")

# --- 辅助函数 ---
def get_ext(filename):
    base, ext = os.path.splitext(filename)
    if not ext: return ".unknown"
    return ext.lower()

def is_target_file(href):
    # 宽松检查：只要包含指定后缀即可
    valid = ['.pdf', '.xlsx', '.xls', '.csv', '.docx', '.doc', '.zip']
    return any(href.lower().endswith(ext) for ext in valid)

def get_file_size_mb(url):
    try:
        # V23 修复：请求前先处理 URL 中的空格
        safe_url = url.replace(" ", "%20")
        r = requests.head(safe_url, verify=False, timeout=5)
        return int(r.headers.get('Content-Length', 0)) / (1024 * 1024)
    except: return 0

# --- 主界面 ---
st.title("🕵️ OSINT 下载器 (V23 空格修复版)")
st.caption("支持：自动扫描网页 / 手动粘贴链接列表")

if 'found_files' not in st.session_state: st.session_state['found_files'] = []

# === 选项卡 ===
tab1, tab2 = st.tabs(["🔗 模式一：自动扫描网页", "📋 模式二：粘贴链接列表"])

with tab1:
    target_url = st.text_input("目标网址", placeholder="https://...")
    if st.button("🚀 扫描网页", key="btn_scan"):
        if target_url:
            try:
                with st.spinner("扫描中..."):
                    headers = {"User-Agent": "Mozilla/5.0"}
                    r = requests.get(target_url, headers=headers, verify=False)
                    soup = BeautifulSoup(r.text, 'html.parser')
                    files = []
                    for a in soup.find_all('a', href=True):
                        if is_target_file(a['href']):
                            full_url = urljoin(target_url, a['href'])
                            name = os.path.basename(unquote(urlparse(full_url).path))
                            if not any(f['URL'] == full_url for f in files):
                                files.append({"下载?": False, "序号": len(files)+1, "文件名": name, "URL": full_url})
                    st.session_state['found_files'] = files
                    st.success(f"扫描完成！发现 {len(files)} 个文件")
            except Exception as e: st.error(str(e))

with tab2:
    st.info("💡 提示：将 Link Gopher 提取的链接粘贴到下方。支持带空格的 URL。")
    raw_text = st.text_area("在此粘贴链接 (每行一个)", height=150)
    
    if st.button("🔍 解析链接", key="btn_parse"):
        if raw_text:
            # === V23 核心修复：改用 splitlines() 按行切割，保护空格 ===
            lines = raw_text.splitlines()
            files = []
            for line in lines:
                line = line.strip() # 去除首尾不可见字符
                if not line: continue
                
                # 只要这行文字里有 http 和 .pdf 就可以
                if "http" in line and is_target_file(line):
                    # 提取 URL (假设整行就是 URL)
                    # 如果有前缀杂质，尝试定位 http
                    http_pos = line.find("http")
                    clean_url = line[http_pos:]
                    
                    # 提取文件名
                    try:
                        name = os.path.basename(unquote(urlparse(clean_url).path))
                    except:
                        name = "unknown_file.pdf"
                        
                    if not any(f['URL'] == clean_url for f in files):
                        files.append({"下载?": False, "序号": len(files)+1, "文件名": name, "URL": clean_url})
            
            st.session_state['found_files'] = files
            if files:
                st.success(f"成功解析出 {len(files)} 个文件！请在下方下载。")
            else:
                st.warning("未发现有效链接。请确认粘贴内容每行包含一个 http...pdf 链接。")

# --- 通用下载区 ---
if st.session_state['found_files']:
    st.markdown("---")
    st.subheader(f"📥 准备下载 ({len(st.session_state['found_files'])} 个文件)")
    
    # 区间选择
    c1, c2, c3, c4 = st.columns([1,1,2,2])
    with c1: start = st.number_input("起始", 1, value=1)
    with c2: end = st.number_input("结束", 1, value=len(st.session_state['found_files']))
    
    if c3.button("✅ 选中此范围"):
        for f in st.session_state['found_files']:
            f['下载?'] = (start <= f['序号'] <= end)
    
    if c4.button("🗑️ 清空所有"):
        for f in st.session_state['found_files']: f['下载?'] = False

    # 表格
    df = pd.DataFrame(st.session_state['found_files'])
    edited_df = st.data_editor(
        df, 
        height=400, 
        key="editor", 
        hide_index=True, 
        column_config={"URL": st.column_config.LinkColumn()}
    )
    
    # 下载逻辑
    selected = edited_df[edited_df["下载?"] == True]
    count = len(selected)
    
    if st.button(f"📦 开始下载 ({count} 个文件)", type="primary"):
        if count > 0:
            zip_buffer = io.BytesIO()
            progress_text = st.empty()
            my_bar = st.progress(0)
            
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                total = len(selected)
                for i, (index, row) in enumerate(selected.iterrows()):
                    try:
                        progress_text.text(f"正在下载 ({i+1}/{total}): {row['文件名']}")
                        headers = {"User-Agent": "Mozilla/5.0"}
                        
                        # === V23 修复：下载时自动把空格转为 %20 ===
                        download_url = row['URL'].replace(" ", "%20")
                        
                        sz = get_file_size_mb(download_url)
                        if sz > 100: 
                            st.toast(f"跳过大文件: {row['文件名']}", icon="⚠️")
                            continue
                            
                        r = requests.get(download_url, headers=headers, verify=False, timeout=60)
                        zf.writestr(row['文件名'], r.content)
                        my_bar.progress((i + 1) / total)
                    except Exception as e: 
                        print(e)
            
            my_bar.empty()
            progress_text.text("✅ 打包完成！")
            st.download_button("🚀 保存 ZIP", zip_buffer.getvalue(), "Epstein_Files.zip", "application/zip", type="primary")
