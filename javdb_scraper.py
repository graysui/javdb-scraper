import os
import re
import json
import time
import pandas as pd
from tqdm import tqdm
from DrissionPage import ChromiumPage, ChromiumOptions
from DrissionPage.common import Settings  # ✅ 添加这行导入
from multiprocessing import Pool
from subprocess import check_output

Settings.set_singleton_tab_obj(False)

# === 设置 ===
SLEEP_TIME = 5  # 每个番号页面等待秒数
CSV_FILENAME = "result.csv"
COOKIE_FILE = "cookies.json"  # 存储Cookie的文件名
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"  # 浏览器路径

# === 内置 Cloudflare 绕过类 ===
class CloudflareBypasser:
    def __init__(self, page, max_retries=5):
        self.page = page
        self.max_retries = max_retries

    def bypass(self):
        """尝试绕过 Cloudflare 验证"""
        try:
            if self.is_cloudflare_page():
                print("🛡️ 检测到 Cloudflare 验证,正在尝试绕过...")
                time.sleep(3)
                
                for _ in range(self.max_retries):
                    if not self.is_cloudflare_page():
                        print("✅ Cloudflare 验证通过")
                        return True
                    
                    try:
                        # 查找验证 iframe
                        iframe = self.page.get_frame('@src^https://challenges.cloudflare.com')
                        if iframe:
                            btn = iframe.ele('css:input[type=checkbox]', timeout=2)
                            if btn:
                                btn.click()
                                time.sleep(2)
                            else:
                                iframe.ele('tag:body').click()
                    except:
                        pass
                    
                    print("⏳ 等待跳转...")
                    time.sleep(2)
                
                print("⚠️ Cloudflare 绕过尝试结束,请检查页面是否已加载")
            else:
                pass

        except Exception as e:
            print(f"❌ 绕过脚本出错: {e}")

    def is_cloudflare_page(self):
        try:
            title = self.page.title.lower()
            return "just a moment" in title or "cloudflare" in title or "attention required" in title
        except:
            return False

# === 辅助函数 ===
def select_folder_dialog():
    if os.name == "nt":
        script = """
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $null = $dialog.ShowDialog()
        $dialog.SelectedPath
        """
        try:
            output = check_output(["powershell", "-Command", script], text=True)
            return output.strip()
        except Exception:
            pass
    folder = input("请输入影片文件夹路径：").strip()
    while not os.path.exists(folder):
        folder = input("❌ 文件夹不存在,请重新输入：").strip()
    return folder

def worker(path):
    """独立的worker函数"""
    try:
        return [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    except:
        return []

def collect_all_filenames(folder):
    if not os.path.isdir(folder):
        raise ValueError(f"路径不存在或不是目录: {folder}")

    start_time = time.time()
    all_files = set()

    try:
        # 简单判断文件量,决定是否启用多进程
        # 注意：os.walk 这里的计数仅作参考
        count = 0
        for _, _, files in os.walk(folder):
            count += len(files)
            if count > 50000: 
                break
            
        if count < 50000:
            for root, _, files in os.walk(folder):
                all_files.update(files)
        else:
            with Pool(processes=min(8, os.cpu_count())) as pool:
                dirs_to_scan = []
                for root, dirs, _ in os.walk(folder):
                    dirs_to_scan.extend(os.path.join(root, d) for d in dirs)
                dirs_to_scan.append(folder)
                
                chunk_size = max(1, len(dirs_to_scan) // (os.cpu_count() * 2))
                results = pool.map(worker, dirs_to_scan, chunksize=chunk_size)
                
                for files in results:
                    all_files.update(files)
                    
        print(f"扫描完成,共 {len(all_files)} 个文件,耗时 {time.time()-start_time:.2f} 秒")
        return all_files
        
    except Exception as e:
        print(f"扫描出错,改用保守方案: {e}")
        return set(f for _, _, files in os.walk(folder) for f in files)

def prompt_url():
    url = input("请输入JAVDB页面链接（例如 https://javdb.com/censored）：").strip()
    if not url:
        print("未输入链接,程序退出")
        exit()
    if "?t=" not in url and "search?q" not in url:
        url += "?t=d"  # 默认按日期排序
    return url

def parse_size(text):
    try:
        match = re.search(r"([\d.]+)\s*(GB|MB)", text, re.IGNORECASE)
        if not match:
            return 0
        size = float(match[1])
        unit = match[2].upper()
        return size * 1024 if unit == "GB" else size
    except:
        return 0

def is_login_page(page):
    try:
        login_form = page.ele('xpath://form[contains(@action, "user_sessions")]', timeout=3)
        login_text = page.ele('xpath://*[contains(text(), "登入") or contains(text(), "登录")]', timeout=3)
        return bool(login_form) or bool(login_text)
    except:
        return False

def load_cookies(page):
    """✅ 改进版：增加空文件和格式错误检查"""
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:  # ✅ 检查文件是否为空
                    print("⚠️ Cookie文件为空")
                    return False
                    
                cookies_list = json.loads(content)
                if not cookies_list:  # ✅ 检查是否有cookie
                    print("⚠️ Cookie列表为空")
                    return False
                    
                page.set.cookies(cookies_list)
                print("✅ Cookie加载成功")
                return True
        except json.JSONDecodeError as e:
            print(f"❌ Cookie文件格式错误: {e}")
            print("🗑️ 正在删除损坏的Cookie文件...")
            os.remove(COOKIE_FILE)
            return False
        except Exception as e:
            print(f"❌ Cookie加载失败: {e}")
    return False

def save_cookies(page):
    try:
        cookies = page.cookies()  # 获取cookies
        with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        print("✅ Cookie已保存")
        return True
    except Exception as e:
        print(f"❌ 保存Cookie失败: {e}")
        return False

def handle_login(page):
    """✅ 改进版：增加详细提示和重试机制"""
    if is_login_page(page):
        print("\n🔒 检测到需要登录")
        print("=" * 50)
        print("操作步骤：")
        print("1. 在自动打开的浏览器中手动登录")
        print("2. 登录成功后,按回车键继续")
        print("=" * 50)
        input("👉 按回车键继续...")
        
        # ✅ 跳转到首页确认登录状态
        print("⏳ 正在验证登录状态...")
        page.get("https://javdb.com/")
        time.sleep(2)
        
        # 再次检查
        if not is_login_page(page):
            print("✅ 登录验证成功！")
            save_cookies(page)
            return True
        else:
            print("❌ 登录验证失败")
            print("💡 提示：请确保已完整登录并看到用户头像")
            retry = input("是否重试？(y/n): ").lower()
            if retry == 'y':
                return handle_login(page)  # 递归重试
            return False
    return True

def main():
    # 1. 配置浏览器路径
    co = ChromiumOptions()
    co.set_browser_path(CHROME_PATH)
    
    # 2. 启动浏览器
    try:
        page = ChromiumPage(addr_or_opts=co)
    except Exception as e:
        print(f"无法启动浏览器,请检查路径是否正确: {CHROME_PATH}")
        print(f"错误信息: {e}")
        return

    # 3. 获取输入信息
    url = prompt_url()
    folder = select_folder_dialog()
    
    if not folder: 
        print("未选择文件夹,程序退出")
        return

    local_files = collect_all_filenames(folder)
    print(f"📁 本地共发现 {len(local_files)} 个文件\n")
    
    # 4. 处理登录和 Cloudflare
    page.get("https://javdb.com/")  # 先访问首页
    
    cf = CloudflareBypasser(page)
    cf.bypass()

    if not load_cookies(page):
        print("尝试进入登录页面...")
        page.get("https://javdb.com/login")
        cf.bypass()
        if not handle_login(page):
            print("❌ 登录流程未通过,程序终止")
            return
    else:
        # 加载了 cookie 也要刷新一下确保生效
        page.refresh()

    # 5. 开始抓取循环
    results = []
    while url:
        print(f"\n🌐 正在加载页面：{url}")
        page.get(url)
        cf.bypass()  # 翻页也可能触发验证

        items = page.eles("css:div.item a.box")
        if not items:
            print("⚠️ 未找到任何列表项,可能页面结构变了或加载失败")
            # 尝试检查是不是翻页过快导致的验证
            if cf.is_cloudflare_page():
                cf.bypass()
                continue
            break

        for item in tqdm(items, desc="📃 列表进度", unit="部"):
            tab = None
            try:
                # 有时候 item 可能会失效,重新获取 text
                title = item.attr("title")
                href = item.attr("href")
                code_text_ele = item.ele(".video-title")
                if not code_text_ele: 
                    continue
                
                code_text = code_text_ele.text
                code = code_text.split(" ")[0]

                # print(f"\n📄 抓取：{code}") 
                
                # 新标签页打开详情
                tab = page.new_tab(href)
                
                # 稍微等待加载
                try:
                    tab.wait.doc_loaded(timeout=10)
                except:
                    pass
                
                # 详情页也可能有 Cloudflare
                # 这里简单处理：如果详情页卡在验证,直接跳过或等待
                # 真正的 bypasser 需要传入 tab 对象,这里为了简化,暂时不处理详情页的强验证
                
                # 获取番号（有些详情页的番号和列表不一样,以详情页为准）
                code_btn = tab.ele("css:.panel-block.first-block a.button.copy-to-clipboard")
                code_real = code_btn.attr("data-clipboard-text") if code_btn else code

                # 匹配本地文件
                matched_file = next((f for f in local_files if code_real in f), "")
                status = "已下载" if matched_file else "未下载"

                best_magnet = ""
                
                # 只有未下载的才去解析磁力,节省时间（可选）
                # if not matched_file: 
                try:
                    # 等待磁力链接区域
                    magnets_container = tab.ele('#magnets-content', timeout=2)
                    if magnets_container:
                        magnets = magnets_container.eles('css:.item')
                        max_size = 0
                        for m in magnets:
                            magnet_link = ""
                            size_text = ""
                            try:
                                copy_btn = m.ele('css:.copy-to-clipboard')
                                if copy_btn:
                                    magnet_link = copy_btn.attr('data-clipboard-text')
                                
                                meta = m.ele('css:.meta')
                                if meta:
                                    size_text = meta.text.strip()
                                    
                                size = parse_size(size_text)

                                if not best_magnet: 
                                    best_magnet = magnet_link
                                if size > max_size:
                                    max_size = size
                                    best_magnet = magnet_link
                            except:
                                continue
                except Exception as e:
                    # print(f"磁力解析微小错误: {e}")
                    pass

                results.append({
                    "番号": code_real,
                    "标题": title,
                    "磁力链接": best_magnet or "无磁力链接",
                    "状态": status,
                    "匹配文件名": matched_file,
                })
                
                # 稍微休眠防止被封
                time.sleep(1) 

            except Exception as e:
                print(f"⚠️ 处理单条出错：{e}")
            finally:
                # 无论如何关闭标签页
                if tab:
                    try:
                        page.close_tabs(tab)
                    except:
                        pass

        # 翻页逻辑
        next_btn = page.ele('css:nav.pagination a[rel=next]', timeout=3)
        if next_btn:
            url = next_btn.attr("href")
            print(f"➡️ 准备翻页: {url}")
            time.sleep(SLEEP_TIME)
        else:
            print("🏁 没有下一页了,任务结束")
            url = None

    # 保存结果
    if results:
        df = pd.DataFrame(results)
        df.to_csv(CSV_FILENAME, index=False, encoding="utf-8-sig")
        print(f"\n✅ 所有任务完成,已抓取 {len(results)} 条,结果保存为 {CSV_FILENAME}")
    else:
        print("\n⚠️ 未抓取到任何数据")

if __name__ == "__main__":
    # Windows下多进程必须放在 main 保护块中
    main()

