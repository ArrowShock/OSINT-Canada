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

# --- 🎨 CSS ---
st.markdown("""
    <style>
    .block-container { padding-top: 2rem !important; padding-bottom: 1rem !important; }
    h1 { margin-bottom: 0.5rem !important; }
    .compact-divider { border-top: 1px solid #e6e6e6; margin-top: 10px; margin-bottom: 15px; }
    .step-header { font-size: 22px; font-weight: 700; color: #0f52ba; margin-bottom: 10px; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; }
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

def get_file_size_mb(url):
    try:
        response = requests.head(url, verify=False, timeout=5)
        size_bytes = int(response.headers.get('Content-Length', 0))
        return size_bytes / (1024 * 1024)
    except:
        return 0

# --- 主界面 ---
st.title("🕵️ OSINT 云端批量下载器")

st.markdown("""
    <div style="margin-bottom: 10px;">
        <span class="feature-tag">🛡️ 智能防崩溃</span>
        <span class="feature-tag">🔄 完美双向同步</span>
        <span class="feature-tag">⚓ 滚动条绝对锁定</span>
    </div>
    <div class="compact-divider"></div> 
""", unsafe_allow_html=True)

if 'found_files' not in st.session_state: st.session_state['found_files'] = []

# ==========================================
# 🧠 核心逻辑：在渲染 UI 之前处理数据交互
# ==========================================

# 1. 检查表格是否有手动更新 (从 session_state.editor 读取)
if "editor" in st.session_state:
    edited_rows = st.session_state.editor.get("edited_rows", {})
    # 如果有修改，立即同步到 source of truth
    if edited_rows:
        for idx, changes in edited_rows.items():
            if "下载?" in changes:
                st.session_state['found_files'][int(idx)]['下载?'] = changes["下载?"]
        
        # 立即计算新的范围，更新 session_state 中的 batch_start/end
        # 这样等下渲染输入框时，数字就是对的！
        selected = [f for f in st.session_state['found_files'] if f['下载?']]
        if selected:
            nums = [f['序号'] for f in selected]
            st.session_state.batch_start = min(nums)
            st.session_state.batch_end = max(nums)

# 2. 按钮回调函数 (保持不变，用于批量操作)
def apply_range_select():
    start = st.session_state.batch_start
    end = st.session_state.batch_end
    for f in st.session_state['found_files']:
        if start <= f['序号'] <= end:
            f['下载?'] = True
        else:
            f['下载?'] = False

def apply_reset():
    for f in st.session_state['found_files']:
        f['下载?'] = False
    st.session_state.batch_start = 1
    st.session_state.batch_end = 1


# --- Step 1 ---
st.markdown('<div class="step-header">Step 1. 扫描文件列表</div>', unsafe_allow_html=True)

col_input, col_btn = st.columns([3, 1], vertical_alignment="bottom")
with col_input:
    target_url = st.text_input("URL", placeholder="输入网址...", label_visibility="collapsed")
with col_btn:
    start_scan = st.button("🚀 开始扫描", type="secondary", use_container_width=True)

if start_scan:
    if not target_url:
        st.warning("请先输入网址！")
    else:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
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
                        if '.' not in raw_name[-5:]: 
                            if 'pdf' in href.lower(): raw_name += '.pdf'
                            else: raw_name += '.html'
                        
                        link_text = a_tag.get_text(strip=True)
                        display_name = link_text if len(link_text) > 3 else raw_name
                        
                        files.append({
                            "下载?": False,
                            "序号": len(files) + 1,
                            "文件名": display_name,
                            "原始文件名": raw_name,
                            "URL": full_url
                        })
                
                st.session_state['found_files'] = files
                st.toast(f"扫描完成！发现 {len(files)} 个文件。", icon="✅")
                # 扫描后如果有Editor状态残留，可以清理一下，但这不重要
                
        except Exception as e:
            st.error(f"扫描失败: {e}")

# --- Step 2 ---
if st.session_state['found_files']:
    st.markdown('<div class="compact-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="step-header">Step 2. 选择与下载</div>', unsafe_allow_html=True)
    
    # === 智能选择器 ===
    with st.container():
        if 'batch_start' not in st.session_state: st.session_state.batch_start = 1
        if 'batch_end' not in st.session_state: st.session_state.batch_end = min(len(st.session_state['found_files']), 30)

        c1, c2, c3, c4 = st.columns([1, 1, 1.5, 3], vertical_alignment="bottom")
        
        with c1: 
            # 这里的 batch_start 已经在上面的预处理逻辑中更新过了！
            st.number_input("起始 ID", min_value=1, key="batch_start")
        with c2: 
            st.number_input("结束 ID", min_value=1, key="batch_end")
            
        with c3:
            st.button("✅ 仅选中此范围", on_click=apply_range_select, help="取消其他，只选当前")

        with c4:
             st.button("🗑️ 重置所有", on_click=apply_reset)

    # === 表格区域 ===
    # 将 session state 转为 DF 用于显示
    df_display = pd.DataFrame(st.session_state['found_files'])
    
    edited_df = st.data_editor(
        df_display,
        column_config={
            "下载?": st.column_config.CheckboxColumn("选?", width="small"),
            "序号": st.column_config.NumberColumn("No.", width="small", format="%d"),
            "URL": st.column_config.LinkColumn("链接"),
        },
        disabled=["序号", "文件名", "原始文件名", "URL"],
        hide_index=True,
        use_container_width=True,
        height=400,
        key="editor" 
        # 注意：这里去掉了所有 on_change，让 Streamlit 自然处理
    )
    
    # --- 下载区域 ---
    # 直接使用 found_files (source of truth)
    selected_rows = [f for f in st.session_state['found_files'] if f['下载?']]
    count = len(selected_rows)
    
    st.info(f"当前选中: {count} 个文件")

    if st.button(f"📦 安全下载 ({count} 个文件)", type="primary"):
        if count == 0:
            st.warning("请至少勾选一个文件！")
        else:
            zip_buffer = io.BytesIO()
            headers = {"User-Agent": "Mozilla/5.0"}
            progress_bar = st.progress(0)
            status_text = st.empty()
            error_log = []
            
            download_list = selected_rows
            total = len(download_list)
            success_count = 0
            
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for i, item in enumerate(download_list):
                    try:
                        file_mb = get_file_size_mb(item['URL'])
                        
                        if file_mb > 100: 
                            status_text.warning(f"⚠️ 跳过大文件 ({file_mb:.1f}MB): {item['原始文件名']}")
                            error_log.append(f"跳过(太大): {item['原始文件名']}")
                            time.sleep(0.5)
                            continue
                        
                        status_text.text(f"下载中 ({i+1}/{total}): {item['原始文件名']}...")
                        r = requests.get(item['URL'], headers=headers, verify=False, timeout=60)
                        zf.writestr(item['原始文件名'], r.content)
                        success_count += 1
                        time.sleep(1)
                    except Exception as e:
                        error_log.append(f"失败: {item['原始文件名']}")
                        pass
                    progress_bar.progress((i + 1) / total)
            
            status_text.success(f"完成！成功: {success_count}, 跳过/失败: {len(error_log)}")
            if error_log:
                st.warning("以下文件未下载（可能太大）：")
                st.write(error_log)
            
            progress_bar.empty()
            
            if success_count > 0:
                st.download_button(
                    label=f"🚀 下载 ZIP ({success_count} 个文件)",
                    data=zip_buffer.getvalue(),
                    file_name=f"OSINT_Files_{int(time.time())}.zip",
                    mime="application/zip",
                    type="primary"
                )
