import streamlit as st
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin, urlparse, unquote
import io
import zipfile
import urllib3
import time
import pandas as pd # <--- 引入 Pandas 表格神器

# --- 🤫 屏蔽 SSL 警告 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 页面配置 ---
st.set_page_config(page_title="OSINT 案件追踪下载器", layout="wide", page_icon="🕵️")

# --- CSS 美化 ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; min-height: 60px; font-size: 18px; font-weight: 700; }
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
st.title("🕵️ OSINT 案件追踪下载器 (表格精选版)")
st.caption("📋 专为长期追踪设计：像 Excel 一样筛选、排序、勾选您需要的“增量文件”")
st.markdown("---")

target_url = st.text_input("🔗 输入目标网址:", placeholder="https://...")

if 'found_files' not in st.session_state: st.session_state['found_files'] = []

# --- 1. 扫描 ---
if st.button("🔍 1. 扫描文件列表"):
    if not target_url:
        st.warning("请先输入网址！")
    else:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
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
                        # 简单的后缀补全
                        if '.' not in raw_name[-5:]: 
                            if 'pdf' in href.lower(): raw_name += '.pdf'
                            else: raw_name += '.html'
                        
                        link_text = a_tag.get_text(strip=True)
                        display_name = link_text if len(link_text) > 3 else raw_name
                        
                        # 构建数据行
                        files.append({
                            "下载?": False,  # 默认不勾选 (方便只选新的)
                            "文件名": display_name,
                            "类型": get_ext(raw_name).upper().replace(".", ""),
                            "原始文件名": raw_name,
                            "URL": full_url
                        })
                
                st.session_state['found_files'] = files
                st.success(f"扫描完成！发现 {len(files)} 个文件。请在下方表格勾选。")
                
        except Exception as e:
            st.error(f"扫描失败: {e}")

# --- 2. 表格选择与下载 ---
if st.session_state['found_files']:
    st.markdown("---")
    st.subheader("2️⃣ 请勾选您需要的文件")
    
    # 将列表转换为 DataFrame (表格数据)
    df = pd.DataFrame(st.session_state['found_files'])
    
    # 显示交互式表格
    edited_df = st.data_editor(
        df,
        column_config={
            "下载?": st.column_config.CheckboxColumn(
                "下载?",
                help="勾选以加入下载列表",
                default=False,
            ),
            "URL": st.column_config.LinkColumn("链接 (点击预览)"),
        },
        disabled=["文件名", "类型", "原始文件名", "URL"], # 只有第一列可以编辑
        hide_index=True,
        use_container_width=True,
        height=500 # 表格高度，太长会有滚动条
    )
    
    # 提取被勾选的行
    selected_rows = edited_df[edited_df["下载?"] == True]
    
    # 显示选中数量
    st.info(f"已选中 {len(selected_rows)} 个文件。")

    # 3. 下载按钮
    if st.button(f"📦 下载选中的 {len(selected_rows)} 个文件"):
        if len(selected_rows) == 0:
            st.warning("您还没勾选任何文件！")
        else:
            zip_buffer = io.BytesIO()
            headers = {"User-Agent": "Mozilla/5.0"}
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 将 DataFrame 转回列表以便循环
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
                        time.sleep(1) # 礼貌等待
                    except:
                        pass
                    progress_bar.progress((i + 1) / total)
            
            status_text.text("打包完成！")
            progress_bar.empty()
            
            st.download_button(
                label=f"🚀 点击下载 ZIP ({success_count} 个文件)",
                data=zip_buffer.getvalue(),
                file_name="Selected_Case_Files.zip",
                mime="application/zip",
                type="primary"
            )
