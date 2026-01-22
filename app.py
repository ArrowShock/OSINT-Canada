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

# ==========================================
# 🧠 核心回调：原地修改内存对象 (In-Place Mutation)
# ==========================================

def handle_editor_change():
    """当表格被修改时触发"""
    # 获取修改记录
    changes = st.session_state.editor_key.get("edited_rows", {})
    
    if changes:
        # 直接修改 session_state 中的 DataFrame 对象，不创建新的
        # 这样 Streamlit 会认为对象 ID 没变，从而尽可能保留前端状态
        for idx, row_changes in changes.items():
            if "下载?" in row_changes:
                st.session_state.main_df.at[int(idx), "下载?"] = row_changes["下载?"]
        
        # 同步更新输入框的数字
        selected = st.session_state.main_df[st.session_state.main_df["下载?"]]
        if not selected.empty:
            st.session_state.batch_start = int(selected["序号"].min())
            st.session_state.batch_end = int(selected["序号"].max())

def apply_range_btn():
    """按钮点击：仅选中范围"""
    start = st.session_state.batch_start
    end = st.session_state.batch_end
    # 向量化原地更新
    st.session_state.main_df["下载?"] = st.session_state.main_df["序号"].between(start, end)

def apply_reset_btn():
    """按钮点击：重置"""
    st.session_state.main_df["下载?"] = False
    st.session_state.batch_start = 1
    st.session_state.batch_end = 1

# --- 主界面 ---
st.title("🕵️ OSINT 云端批量下载器")

st.markdown("""
    <div style="margin-bottom: 10px;">
        <span class="feature-tag">🛡️ 智能防崩溃</span>
        <span class="feature-tag">🔄 完美双向同步</span>
        <span class="feature-tag">⚓ 内存级防抖动</span>
    </div>
    <div class="compact-divider"></div> 
""", unsafe_allow_html=True)

# 确保 main_df 存在且持久
if 'main_df' not in st.session_state:
    st.session_state.main_df = pd.DataFrame()

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
                
                # 初始化/覆盖 main_df
                st.session_state.main_df = pd.DataFrame(files)
                st.toast(f"扫描完成！发现 {len(files)} 个文件。", icon="✅")
                
        except Exception as e:
            st.error(f"扫描失败: {e}")

# --- Step 2 ---
if not st.session_state.main_df.empty:
    st.markdown('<div class="compact-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="step-header">Step 2. 选择与下载</div>', unsafe_allow_html=True)
    
    # === 智能选择器 ===
    with st.container():
        if 'batch_start' not in st.session_state: st.session_state.batch_start = 1
        # 动态计算最大值，防止索引越界
        max_val = len(st.session_state.main_df)
        if 'batch_end' not in st.session_state: st.session_state.batch_end = min(max_val, 30)

        c1, c2, c3, c4 = st.columns([1, 1, 1.5, 3], vertical_alignment="bottom")
        
        with c1: 
            st.number_input("起始 ID", min_value=1, key="batch_start")
        with c2: 
            st.number_input("结束 ID", min_value=1, key="batch_end")
            
        with c3:
            st.button("✅ 仅选中此范围", on_click=apply_range_btn, help="取消其他，只选当前")

        with c4:
             st.button("🗑️ 重置所有", on_click=apply_reset_btn)

    # === 表格区域 ===
    # 核心：直接传入 session_state.main_df 对象，不要在外面做任何切片或处理
    
    edited_df = st.data_editor(
        st.session_state.main_df,
        column_config={
            "下载?": st.column_config.CheckboxColumn("选?", width="small"),
            "序号": st.column_config.NumberColumn("No.", width="small", format="%d"),
            "URL": st.column_config.LinkColumn("链接"),
        },
        disabled=["序号", "文件名", "原始文件名", "URL"],
        hide_index=True,
        use_container_width=True,
        height=400,
        key="editor_key", # 使用固定 Key
        on_change=handle_editor_change # 回调处理同步
    )
    
    # --- 下载区域 ---
    # 过滤出需要下载的
    selected_rows = st.session_state.main_df[st.session_state.main_df["下载?"]]
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
            
            download_list = selected_rows.to_dict('records')
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
