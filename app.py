import streamlit as st
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin, urlparse, unquote
import io
import zipfile
import urllib3

# --- 🤫 屏蔽 SSL 警告 ---
# 既然我们决定忽略证书，就不要让它一直弹红色的警告文字
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 页面配置 ---
st.set_page_config(page_title="OSINT 云端下载器", layout="wide", page_icon="🕵️")

# --- CSS 美化 ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; min-height: 60px; font-size: 18px; font-weight: 700; }
    .success-log { color: #0f5132; background-color: #d1e7dd; padding: 6px; border-radius: 4px; border-left: 4px solid #198754; margin-bottom: 2px; }
    .badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; color: white; margin-right: 8px; font-weight: bold; }
    .pdf-bg { background-color: #b30b00; }
    .xls-bg { background-color: #1d6f42; }
    .doc-bg { background-color: #2b579a; }
    .zip-bg { background-color: #e6a200; color: black; }
    .other-bg { background-color: #6c757d; }
    </style>
""", unsafe_allow_html=True)

# --- 辅助函数 ---
def get_file_type_badge(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext == '.pdf': return "<span class='badge pdf-bg'>PDF</span>"
    if ext in ['.xlsx', '.xls', '.csv']: return "<span class='badge xls-bg'>EXCEL</span>"
    if ext in ['.docx', '.doc']: return "<span class='badge doc-bg'>WORD</span>"
    if ext in ['.zip', '.rar']: return "<span class='badge zip-bg'>ZIP</span>"
    return f"<span class='badge other-bg'>{ext.upper()}</span>"

def is_target_file(href):
    valid_exts = ['.pdf', '.xlsx', '.xls', '.csv', '.docx', '.doc', '.zip', '.json', '.xml', '.txt']
    return any(href.lower().endswith(ext) for ext in valid_exts) or 'download' in href.lower()

# --- 主界面 ---
st.title("🕵️ OSINT 云端批量下载器")
st.caption("输入网址 -> 扫描 -> 生成 ZIP 包下载 | 无需安装 Python，发给朋友直接用")
st.markdown("---")

target_url = st.text_input("🔗 输入目标网址:", placeholder="https://...")

if 'found_files' not in st.session_state: st.session_state['found_files'] = []

# --- 1. 扫描 ---
if st.button("🔍 1. 扫描文件列表"):
    if not target_url:
        st.warning("请先输入网址！")
    else:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            with st.spinner("正在云端扫描..."):
                # 关键修改：verify=False (忽略证书验证)
                response = requests.get(target_url, headers=headers, verify=False)
                response.raise_for_status() # 检查是否是 404
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
                        if '.' not in raw_name[-5:]: raw_name += '.dat'
                        link_text = a_tag.get_text(strip=True)
                        display_name = link_text if len(link_text) > 3 else raw_name
                        files.append({"name": display_name, "url": full_url, "file": raw_name})
                
                st.session_state['found_files'] = files
                st.success(f"扫描完成！发现 {len(files)} 个文件。")
                
        except Exception as e:
            st.error(f"扫描失败: {e}")

# --- 2. 打包下载 ---
if st.session_state['found_files']:
    st.markdown("---")
    st.subheader(f"2️⃣ 准备下载 ({len(st.session_state['found_files'])})")
    
    with st.expander("点击查看即将下载的文件列表"):
        for item in st.session_state['found_files']:
            badge = get_file_type_badge(item['file'])
            st.markdown(f"<div>{badge} {item['name']}</div>", unsafe_allow_html=True)

    if st.button("📦 开始打包并下载 ZIP"):
        zip_buffer = io.BytesIO()
        headers = {"User-Agent": "Mozilla/5.0"}
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            total = len(st.session_state['found_files'])
            success_count = 0
            
            for i, item in enumerate(st.session_state['found_files']):
                try:
                    status_text.text(f"正在下载: {item['file']}...")
                    # 关键修改：verify=False (忽略证书验证)
                    r = requests.get(item['url'], headers=headers, verify=False)
                    zf.writestr(item['file'], r.content)
                    success_count += 1
                except:
                    pass
                progress_bar.progress((i + 1) / total)
        
        status_text.text("打包完成！")
        progress_bar.empty()
        
        st.download_button(
            label=f"🚀 点击下载 ZIP 压缩包 ({success_count} 个文件)",
            data=zip_buffer.getvalue(),
            file_name="OSINT_Files.zip",
            mime="application/zip",
            type="primary"
        )
