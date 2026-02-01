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
st.set_page_config(page_title="OSINT 下载器 (V25 通行证版)", layout="wide", page_icon="🕵️")

# --- 辅助函数 ---
def is_target_file(href):
    valid = ['.pdf', '.xlsx', '.xls', '.csv', '.docx', '.doc', '.zip']
    return any(href.lower().endswith(ext) for ext in valid)

def safe_encode_url(url):
    parts = urlparse(url)
    safe_path = quote(parts.path) 
    new_url = parts.scheme + "://" + parts.netloc + safe_path
    if parts.query: new_url += "?" + parts.query
    return new_url

# --- 主界面 ---
st.title("🕵️ OSINT 下载器 (V25 通行证版)")
st.caption("新增：Cookie 注入功能，专治 'Access Denied' 年龄验证锁")

if 'found_files' not in st.session_state: st.session_state['found_files'] = []

# === 侧边栏：配置区 ===
with st.sidebar:
    st.header("🔐 身份伪装配置")
    st.info("如果下载的 PDF 打不开或只有 53KB，请在此填入浏览器的 Cookie。")
    user_cookie = st.text_area("_ga=GA1.1.739891733.1767747350; nmstat=b851bd0d-2a3d-eccb-42fb-3f623f20f0b6; _ga_CSLL4ZEK4L=GS2.1.s1769920583$o4$g1$t1769922779$j2$l0$h0; QueueITAccepted-SDFrts345E-V3_usdojsearch=EventId%3Dusdojsearch%26RedirectType%3Dsafetynet%26IssueTime%3D1769922786%26Hash%3D6f3152dc965a89ee6c7c9b80e49518dfd2450c0da055fec55395106f682b10d6; QueueITAccepted-SDFrts345E-V3_usdojfiles=EventId%3Dusdojfiles%26RedirectType%3Dsafetynet%26IssueTime%3D1769923479%26Hash%3Dcc591226f177c714d9387feee5b2e510964acb0adf11d1fda4be9e6047bc955a", height=150, placeholder="例如: SSESSxxx=...; _ga=...")

# === 选项卡 ===
tab1, tab2 = st.tabs(["🔗 模式一：自动扫描网页", "📋 模式二：粘贴链接列表"])

with tab1:
    target_url = st.text_input("目标网址", placeholder="https://...")
    if st.button("🚀 扫描网页"):
        if target_url:
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                if user_cookie: headers["Cookie"] = user_cookie # 注入 Cookie
                
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
    st.info("💡 提示：将 Link Gopher 提取的链接粘贴到下方。")
    raw_text = st.text_area("在此粘贴链接 (每行一个)", height=150)
    
    if st.button("🔍 解析链接"):
        if raw_text:
            lines = raw_text.splitlines()
            files = []
            for line in lines:
                line = line.strip()
                if not line: continue
                if "http" in line and is_target_file(line):
                    http_pos = line.find("http")
                    clean_url = line[http_pos:]
                    try: name = os.path.basename(unquote(urlparse(clean_url).path))
                    except: name = "unknown_file.pdf"
                    if not any(f['URL'] == clean_url for f in files):
                        files.append({"下载?": False, "序号": len(files)+1, "文件名": name, "URL": clean_url})
            st.session_state['found_files'] = files
            if files: st.success(f"成功解析 {len(files)} 个文件")
            else: st.warning("未发现有效链接")

# --- 下载区 ---
if st.session_state['found_files']:
    st.markdown("---")
    st.subheader(f"📥 准备下载 ({len(st.session_state['found_files'])} 个文件)")
    
    c1, c2, c3, c4 = st.columns([1,1,2,2])
    with c1: start = st.number_input("起始", 1, value=1)
    with c2: end = st.number_input("结束", 1, value=len(st.session_state['found_files']))
    if c3.button("✅ 选中范围"):
        for f in st.session_state['found_files']: f['下载?'] = (start <= f['序号'] <= end)
    if c4.button("🗑️ 清空"):
        for f in st.session_state['found_files']: f['下载?'] = False

    df = pd.DataFrame(st.session_state['found_files'])
    edited_df = st.data_editor(df, height=400, key="editor", hide_index=True, column_config={"URL": st.column_config.LinkColumn()})
    
    selected = edited_df[edited_df["下载?"] == True]
    count = len(selected)
    
    if st.button(f"📦 开始下载 ({count} 个文件)", type="primary"):
        if count > 0:
            zip_buffer = io.BytesIO()
            progress_text = st.empty()
            my_bar = st.progress(0)
            
            success = 0
            fail = 0
            
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                total = len(selected)
                for i, (index, row) in enumerate(selected.iterrows()):
                    try:
                        progress_text.text(f"下载中: {row['文件名']}")
                        
                        # === V25 核心：带着 Cookie 去下载 ===
                        download_url = safe_encode_url(row['URL'])
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Referer": "https://www.justice.gov/"
                        }
                        if user_cookie: headers["Cookie"] = user_cookie # <--- 关键！
                        
                        r = requests.get(download_url, headers=headers, verify=False, timeout=60)
                        
                        # 验身：如果还是 HTML，说明 Cookie 没生效
                        content_type = r.headers.get("Content-Type", "").lower()
                        if "html" in content_type and not row['文件名'].endswith(".html"):
                            st.toast(f"身份验证失败(还是网页): {row['文件名']}", icon="🚫")
                            fail += 1
                            continue
                            
                        zf.writestr(row['文件名'], r.content)
                        success += 1
                        my_bar.progress((i + 1) / total)
                    except: fail += 1
            
            my_bar.empty()
            if success > 0:
                progress_text.success(f"✅ 完成！成功: {success}, 失败: {fail}")
                st.download_button("🚀 保存 ZIP", zip_buffer.getvalue(), "Verified_Files.zip", "application/zip", type="primary")
            else:
                progress_text.error("⚠️ 全部失败。请检查 Cookie 是否过期或复制完整。")
