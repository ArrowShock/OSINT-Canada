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

# 屏蔽警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="OSINT 下载器 (极简稳定版)", layout="wide", page_icon="🕵️")

# 辅助函数
def is_target_file(href):
    valid = ['.pdf', '.xlsx', '.xls', '.csv', '.docx', '.doc', '.zip']
    return any(href.lower().endswith(ext) for ext in valid) or 'download' in href.lower()

def get_file_size_mb(url):
    try:
        r = requests.head(url, verify=False, timeout=5)
        return int(r.headers.get('Content-Length', 0)) / (1024 * 1024)
    except: return 0

# 主界面
st.title("🕵️ OSINT 下载器 (极简稳定版)")
st.caption("无同步、无跳转、纯粹的下载工具")

if 'found_files' not in st.session_state: st.session_state['found_files'] = []

# Step 1: 扫描
target_url = st.text_input("目标网址", placeholder="https://...")
if st.button("🚀 扫描"):
    if target_url:
        try:
            with st.spinner("扫描中..."):
                r = requests.get(target_url, headers={"User-Agent": "Mozilla/5.0"}, verify=False)
                soup = BeautifulSoup(r.text, 'html.parser')
                files = []
                for a in soup.find_all('a', href=True):
                    if is_target_file(a['href']):
                        full_url = urljoin(target_url, a['href'])
                        name = os.path.basename(unquote(urlparse(full_url).path))
                        if '.' not in name[-5:]: name += '.pdf'
                        files.append({"下载?": False, "序号": len(files)+1, "文件名": name, "URL": full_url})
                st.session_state['found_files'] = files
                st.success(f"发现 {len(files)} 个文件")
        except Exception as e: st.error(str(e))

# Step 2: 下载
if st.session_state['found_files']:
    st.markdown("---")
    # 简单的区间选择
    c1, c2, c3, c4 = st.columns([1,1,2,2])
    start = c1.number_input("起始", 1, value=1)
    end = c2.number_input("结束", 1, value=min(len(st.session_state['found_files']), 30))
    
    if c3.button("✅ 选中此范围"):
        for f in st.session_state['found_files']:
            f['下载?'] = (start <= f['序号'] <= end)
    
    if c4.button("🗑️ 清空所有"):
        for f in st.session_state['found_files']: f['下载?'] = False

    # 简单的表格 (无回调，无自动同步，因此不会跳)
    df = pd.DataFrame(st.session_state['found_files'])
    edited_df = st.data_editor(df, height=400, key="editor", hide_index=True, 
                               column_config={"URL": st.column_config.LinkColumn()})
    
    # 下载逻辑
    selected = edited_df[edited_df["下载?"] == True]
    count = len(selected)
    
    if st.button(f"📦 下载 ({count} 个文件)", type="primary"):
        if count > 0:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf, st.status("正在下载...") as status:
                for i, row in selected.iterrows():
                    try:
                        sz = get_file_size_mb(row['URL'])
                        if sz > 100: 
                            status.write(f"⚠️ 跳过大文件: {row['文件名']}")
                            continue
                        status.write(f"下载: {row['文件名']}")
                        r = requests.get(row['URL'], verify=False, timeout=60)
                        zf.writestr(row['文件名'], r.content)
                    except: pass
            st.download_button("🚀 保存 ZIP", zip_buffer.getvalue(), "files.zip", "application/zip", type="primary")
