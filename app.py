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

# === 🌟 核心回调系统 (V17 稳定性引擎) ===

def init_df_view(files):
    """初始化或重置 DataFrame 视图"""
    # 我们将 DataFrame 存储在 session_state 中，保持对象 ID 不变
    st.session_state.df_view = pd.DataFrame(files)

def on_editor_change():
    """
    当用户手动勾选表格时触发。
    使用原地更新 (In-place Update) 技术，防止滚动条跳动。
    """
    edited_rows = st.session_state.editor.get("edited_rows", {})
    
    # 1. 更新 DataFrame (直接修改 session_state 中的对象)
    for idx, changes in edited_rows.items():
        if "下载?" in changes:
            # 使用 .at 进行极速原地修改
            st.session_state.df_view.at[int(idx), "下载?"] = changes["下载?"]
    
    # 2. 反向同步：计算新的选中范围，更新输入框
    # 直接读取 df_view 的最新状态
    selected = st.session_state.df_view[st.session_state.df_view["下载?"] == True]
    if not selected.empty:
        # 更新输入框绑定的 session_state 变量
        st.session_state.batch_start = int(selected["序号"].min())
        st.session_state.batch_end = int(selected["序号"].max())

def on_range_select():
    """当点击'仅选中此范围'按钮时触发"""
    start = st.session_state.batch_start
    end = st.session_state.batch_end
    
    # 向量化更新：比 for 循环快 100 倍，且直接作用于 df_view
    st.session_state.df_view["下载?"] = st.session_state.df_view["序号"].between(start, end)

def on_reset():
    """当点击'重置'按钮时触发"""
    st.session_state.df_view["下载?"] = False
    st.session_state.batch_start = 1
    st.session_state.batch_end = 1

# --- 主界面 ---
st.title("🕵️ OSINT 云端批量下载器")

st.markdown("""
    <div style="margin-bottom: 10px;">
        <span class="feature-tag">🛡️ 智能防崩溃</span>
        <span class="feature-tag">🔄 双向同步无报错</span>
        <span class="feature-tag">⚓ 滚动条锁定技术</span>
    </div>
    <div class="compact-divider"></div> 
""", unsafe_allow_html=True)

if 'found_files' not in st.session_state: st.session_state['found_files'] = []
# 确保 df_view 存在
if 'df_view' not in st.session_state: st.session_state.df_view = pd.DataFrame()

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
                # 初始化 DataFrame 视图
                init_df_view(files)
                st.toast(f"扫描完成！发现 {len(files)} 个文件。", icon="✅")
                
        except Exception as e:
            st.error(f"扫描失败: {e}")

# --- Step 2 ---
if not st.session_state.df_view.empty:
    st.markdown('<div class="compact-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="step-header">Step 2. 选择与下载</div>', unsafe_allow_html=True)
    
    # === 智能选择器 ===
    with st.container():
        if 'batch_start' not in st.session_state: st.session_state.batch_start = 1
        if 'batch_end' not in st.session_state: st.session_state.batch_end = min(len(st.session_state['found_files']), 30)

        c1, c2, c3, c4 = st.columns([1, 1, 1.5, 3], vertical_alignment="bottom")
        
        with c1: 
            st.number_input("起始 ID", min_value=1, key="batch_start")
        with c2: 
            st.number_input("结束 ID", min_value=1, key="batch_end")
            
        with c3:
            # 绑定 on_range_select 回调
            st.button("✅ 仅选中此范围", on_click=on_range_select, help="取消其他，只选当前")

        with c4:
             # 绑定 on_reset 回调
             st.button("🗑️ 重置所有", on_click=on_reset)

    # === 表格区域 (稳定性核心) ===
    # 我们直接传入 session_state.df_view
    # 因为对象 ID 没变，Streamlit 会认为"表格主体没变"，因此不会重置滚动条！
    
    edited_df = st.data_editor(
        st.session_state.df_view,
        column_config={
            "下载?": st.column_config.CheckboxColumn("选?", width="small"),
            "序号": st.column_config.NumberColumn("No.", width="small", format="%d"),
            "URL": st.column_config.LinkColumn("链接"),
        },
        disabled=["序号", "文件名", "原始文件名", "URL"],
        hide_index=True,
        use_container_width=True,
        height=400,
        key="editor",
        on_change=on_editor_change # <--- 启用回调，实现双向同步
    )
    
    # --- 下载区域 ---
    # 从 df_view 中提取选中的行
    selected_rows = st.session_state.df_view[st.session_state.df_view["下载?"] == True]
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
            
            # Pandas DF 转字典列表
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
