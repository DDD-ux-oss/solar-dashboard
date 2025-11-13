# -*- coding: utf-8 -*-

import os
import time
import json
import logging
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    WebDriverException, TimeoutException,
    ElementNotInteractableException, NoSuchElementException,
    ElementClickInterceptedException
)
import re
import io
import base64

# 可选的OCR支持
try:
    from PIL import Image
except Exception:
    Image = None
try:
    import pytesseract
except Exception:
    pytesseract = None

# 配置日志
def setup_logging():
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'esolar_scraper.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

class ESolarScraper:
    def __init__(self, username, password, screenshots_dir=None, data_file_path=None):
        self.username = username
        self.password = password
        self.driver = None
        
        # 设置截图目录
        if screenshots_dir:
            self.screenshots_dir = screenshots_dir
        else:
            self.screenshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'screenshots')
        
        # 设置数据保存文件路径
        if data_file_path:
            self.data_file_path = data_file_path
        else:
            self.data_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'solar_data.json')
        
        # 创建截图目录（如果不存在）
        os.makedirs(self.screenshots_dir, exist_ok=True)
        
        # 配置Edge浏览器选项
        self.edge_options = Options()
        
        # 添加兼容性和性能参数
        self.edge_options.add_argument('--disable-software-rasterizer')
        self.edge_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        self.edge_options.add_argument('--disable-site-isolation-trials')
        self.edge_options.add_argument('--no-sandbox')
        self.edge_options.add_argument('--disable-dev-shm-usage')
        self.edge_options.add_argument('--disable-gpu')
        # 添加无头模式配置，仅在CI环境中启用
        # 为了方便本地调试，默认不启用无头模式
        
        # 设置用户代理（使用正确格式，避免Edge打开多个错误页面）
        self.edge_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        )
        
        # 实验性选项
        self.edge_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        self.edge_options.add_experimental_option('detach', False)
        self.edge_options.add_experimental_option('useAutomationExtension', False)
        
        # 禁用自动化控制特征
        self.edge_options.add_argument('--disable-blink-features=AutomationControlled')
        
        # 使用更宽松的浏览器设置以允许网站正常功能运行
        self.edge_options.add_argument('--disable-extensions')
        self.edge_options.add_argument('--disable-notifications')
        self.edge_options.add_argument('--disable-features=TranslateUI')
        
        # 使用简化的内容安全策略，允许必要的资源加载
        # 移除了严格的CSP限制，以避免阻止网站必要功能
        
        # 开启性能日志以捕获Network事件（Chromium驱动支持）
        try:
            self.edge_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        except Exception:
            pass
        
        # 添加基本的首选项设置，保持简单
        self.edge_options.add_experimental_option('prefs', {
            'profile.default_content_setting_values': {
                'images': 1,
                'javascript': 1,
                'plugins': 1,  # 允许必要的插件
                'popups': 1,   # 允许必要的弹窗
                'notifications': 2,  # 阻止通知
            },
            # 移除了过于严格的内容设置异常规则
            'profile.managed_default_content_settings': {
                'images': 1,
                'javascript': 1,
                'plugins': 1,
                'popups': 1,
                'notifications': 2
            },
            # 禁用站点隔离
            'site-isolation-trial-opt-out': True
            })
        
        # 项目容量映射
        self.project_capacities = {
            1: {'dcCapacity': 5.9826, 'acCapacity': 4.77},    # 梁才宋滩
            2: {'dcCapacity': 1.94346, 'acCapacity': 1.7},    # 杨柳雪李赞皇
            3: {'dcCapacity': 5.3749, 'acCapacity': 4.3},     # 滨北南邱家
            4: {'dcCapacity': 1.16938, 'acCapacity': 1},      # 水立方
            5: {'dcCapacity': 0.10384, 'acCapacity': 0.1},    # 黄河植物园
            6: {'dcCapacity': 1.58858, 'acCapacity': 1.58858}  # 零碳商业园
        }
        
        # 项目名称映射
        self.project_names = {
            1: '梁才宋滩',
            2: '杨柳雪李赞皇', 
            3: '滨北南邱家',
            4: '水立方',
            5: '黄河植物园',
            6: '零碳商业园'
        }
    
    def __enter__(self):
        """进入上下文管理器时初始化WebDriver"""
        self.initialize_driver()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
         """退出上下文管理器时关闭WebDriver"""
         try:
             if self.driver:
                 self.driver.quit()
                 logger.info('WebDriver已关闭')
         except Exception as e:
             logger.warning(f'关闭WebDriver时发生异常: {e}')
    
    def initialize_driver(self):
        """初始化WebDriver，不使用CDP命令以避免兼容性问题"""
        try:
            # 获取当前脚本所在目录
            script_dir = os.path.dirname(os.path.abspath(__file__))
            # 假设msedgedriver.exe与脚本在同一目录
            driver_path = os.path.join(script_dir, 'msedgedriver.exe')
            service = None
            
            # 检查驱动文件是否存在
            if os.path.exists(driver_path):
                # 使用指定路径的驱动
                service = Service(driver_path)
                self.driver = webdriver.Edge(service=service, options=self.edge_options)
            else:
                # 使用系统PATH中的驱动，在CI环境中使用ChromeDriver
                logger.info("未找到本地Edge驱动，将使用系统PATH中的驱动")
                self.driver = webdriver.Edge(options=self.edge_options)
            
            # 设置页面加载超时
            self.driver.set_page_load_timeout(30)
            # 设置脚本执行超时
            self.driver.set_script_timeout(30)
            # 设置隐式等待时间
            self.driver.implicitly_wait(10)
            
            logger.info('WebDriver初始化成功，未使用CDP命令以避免兼容性问题')
        except Exception as e:
            logger.error(f'WebDriver初始化失败: {str(e)}')
            raise
    
    def login(self):
        """登录ESolar系统"""
        try:
            if not self.driver:
                self.initialize_driver()
                
            # 访问登录页面
            logger.info(f'正在访问登录页面: https://esolar.tbecloud.com/login')
            self.driver.get('https://esolar.tbecloud.com/login')
            
            # 最大化浏览器窗口
            logger.info('正在最大化浏览器窗口')
            self.driver.maximize_window()
            
            # 简化版的导航拦截脚本，只阻止基本的外部窗口打开
            self.driver.execute_script("""
                // 定义目标域名
                const targetDomain = 'esolar.tbecloud.com';
                
                // 1. 拦截window.open调用
                const originalOpen = window.open;
                window.open = function(url, windowName, features) {
                    if (url && typeof url === 'string' && !url.includes(targetDomain)) {
                        console.log('已阻止打开外部窗口: ' + url);
                        return null;
                    }
                    return originalOpen.apply(this, arguments);
                };
            """)
            
            # 等待页面加载完成，使用更通用的等待条件
            try:
                # 尝试等待body完全加载
                WebDriverWait(self.driver, 15).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                logger.info('页面已完全加载')
            except TimeoutException:
                logger.warning('页面加载可能不完全，但继续尝试登录流程')
            
            # 获取所有class为ant-input的输入框（Ant Design风格）
            try:
                inputs = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, 'ant-input'))
                )
            except:
                # 如果ant-input不存在，尝试回退到el-input__inner
                logger.info('未找到ant-input，尝试使用el-input__inner')
                inputs = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, 'el-input__inner'))
                )
            
            if len(inputs) >= 2:
                # 在第一个输入框中输入用户名
                logger.info(f'正在输入用户名: {self.username}')
                inputs[0].clear()
                inputs[0].send_keys(self.username)
                
                # 在第二个输入框中输入密码
                logger.info('正在输入密码')
                inputs[1].clear()
                inputs[1].send_keys(self.password)
            else:
                logger.error('未找到足够的输入框')
                return False
            
            # 点击复选框（使用用户指定的主选择器）
            try:
                # 使用用户指定的id选择器
                checkbox = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.ID, 'agreement'))
                )
                logger.info('正在点击复选框 (使用ID: agreement)')
                checkbox.click()
            except Exception as e:
                logger.error(f'点击复选框时出错: {str(e)}')
                # 尝试通过JavaScript点击
                try:
                    self.driver.execute_script("document.getElementById('agreement').click();")
                    logger.info('通过JavaScript点击复选框成功')
                except Exception as js_error:
                    logger.error(f'通过JavaScript点击复选框也失败: {str(js_error)}')
            
            # 点击登录按钮（使用用户提供的完整class选择器）
            try:
                # 使用用户提供的完整class选择器
                login_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, '.ant-btn.ant-btn-primary.ant-btn-color-primary.ant-btn-variant-solid.ant-btn-lg.ant-btn-block'))
                )
                logger.info('正在点击Ant Design风格的登录按钮 (使用完整class选择器)')
                login_button.click()
            except Exception as e:
                logger.warning(f'未找到完整class的登录按钮: {str(e)}')
                try:
                    # 尝试使用简化的选择器
                    login_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, '.ant-btn.ant-btn-primary.ant-btn-block'))
                    )
                    logger.info('正在点击登录按钮 (使用简化的选择器)')
                    login_button.click()
                except Exception as alt_error:
                    logger.error(f'点击登录按钮时出错: {str(alt_error)}')
                    # 尝试回退到原始选择器
                    try:
                        login_button = self.driver.find_element(By.CLASS_NAME, 'login_button')
                        login_button.click()
                        logger.info('使用通用选择器点击登录按钮成功')
                    except Exception as final_error:
                        logger.error(f'使用所有选择器点击登录按钮都失败: {str(final_error)}')
                        return False
            
            # 等待登录成功并跳转
            try:
                # 尝试检测登录成功的多种方式
                login_success = False
                
                # 方式1: 检查URL变化
                try:
                    WebDriverWait(self.driver, 8).until(
                        EC.url_contains('#/home')  # 假设登录成功后跳转到包含#/home的URL
                    )
                    logger.info('登录成功: URL包含#/home')
                    login_success = True
                except TimeoutException:
                    logger.info('登录后URL未包含#/home，尝试其他检测方式')
                
                # 方式2: 检查页面标题变化
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.title_contains('首页')  # 假设登录成功后标题包含'首页'
                    )
                    logger.info('登录成功: 页面标题包含"首页"')
                    login_success = True
                except TimeoutException:
                    logger.info('页面标题未包含"首页"')
                
                # 方式3: 检查是否存在登出按钮或其他登录后特有的元素
                try:
                    # 等待3秒让页面完全加载
                    time.sleep(3)
                    
                    # 打印当前URL和页面标题，用于调试
                    current_url = self.driver.current_url
                    current_title = self.driver.title
                    logger.info(f'当前URL: {current_url}')
                    logger.info(f'当前页面标题: {current_title}')
                    
                    # 尝试获取页面内容的一小部分，用于调试
                    page_source_preview = self.driver.page_source[:500]  # 获取前500个字符
                    logger.debug(f'页面源码预览: {page_source_preview}')
                    
                    # 检查是否存在登出按钮或其他登录后特有的元素
                    # 这里使用一个通用的检查方法，查看页面是否有明显变化
                    body_text = self.driver.find_element(By.TAG_NAME, 'body').text
                    if '登录' not in body_text and len(body_text) > 100:
                        logger.info('登录成功: 页面内容已更新，不再包含"登录"字样且内容丰富')
                        login_success = True
                except Exception as e:
                    logger.error(f'检查页面内容时出错: {str(e)}')
                
                # 如果任一检测方式成功，认为登录成功
                if login_success:
                    logger.info(f'登录成功')
                    return True
                else:
                    logger.warning('所有登录成功检测方式均失败，可能登录失败或页面结构与预期不同')
                    
                    # 已按用户要求移除登录调试截图
                    
                    # 检查是否有登录失败的提示
                    try:
                        error_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'error') or contains(@class, 'message')]")
                        if error_elements:
                            for element in error_elements:
                                if element.is_displayed():
                                    logger.error(f'可能的错误提示: {element.text}')
                    except Exception as e:
                        logger.error(f'检查错误提示时出错: {str(e)}')
                    
                    return False
            except Exception as e:
                logger.error(f'登录结果检测过程中发生错误: {str(e)}')
                
                # 已按用户要求移除登录错误截图
                
                return False
            
        except Exception as e:
            logger.error(f'登录过程中出错: {str(e)}')
            
            # 已按用户要求移除登录错误截图
            
            return False
    
    def close_all_modals(self):
        """关闭所有 iView 弹窗（优先 primary 按钮）"""
        try:
            while True:
                modals = self.driver.find_elements(By.CLASS_NAME, "ivu-modal")
                if not modals:
                    logger.info("所有模态框已关闭")
                    break

                modal = modals[0]  # 每次只处理第一个

                try:
                    # 优先等待 primary 按钮可点击
                    logger.info("尝试查找并点击footer中的primary按钮")
                    close_btn = WebDriverWait(modal, 3).until(
                        EC.element_to_be_clickable(
                            (By.CSS_SELECTOR, ".ivu-modal-footer .ivu-btn.ivu-btn-primary")
                        )
                    )
                    # 滚动按钮到视口内
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", close_btn)
                    
                    # 使用ActionChains点击（兼容被覆盖或动画延迟）
                    ActionChains(self.driver).move_to_element(close_btn).click().perform()
                    logger.info("成功点击primary按钮关闭模态框")
                    
                    # 等待模态框消失
                    WebDriverWait(self.driver, 5).until(EC.staleness_of(modal))
                except Exception as e:
                    logger.warning(f"primary按钮未找到或点击失败: {e}")
                    try:
                        # 尝试直接移除模态框
                        logger.info("尝试直接通过JavaScript移除模态框元素")
                        self.driver.execute_script("arguments[0].remove();", modal)
                        time.sleep(1)  # 给DOM一些时间来更新
                        logger.info("通过JavaScript移除模态框成功")
                    except Exception as js_error:
                        logger.error(f"移除模态框失败: {js_error}")
                        # 已按用户要求移除模态框调试截图
        except Exception as e:
            logger.error(f"关闭所有模态框失败: {e}")
        
        # 无论如何都返回True，确保后续操作可以继续执行
        return True

    def _collect_tooltip_text(self):
        """收集ECharts悬浮提示文本，扩展选择器集合并按显示优先返回文本"""
        try:
            selectors = [
                "div.echarts-tooltip",
                "div.echarts-tooltip-wrap",
                "div.zr-tooltip",
                "div.tooltip",
                "div[class*='tooltip']",
            ]
            for sel in selectors:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    if el and el.is_displayed():
                        txt = (el.text or "").strip()
                        if not txt:
                            try:
                                html = (el.get_attribute('innerHTML') or '').strip()
                                if html:
                                    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
                                    html = re.sub(r"<[^>]+>", "", html)
                                    txt = html.strip()
                            except Exception:
                                pass
                        if txt:
                            return txt
                except Exception:
                    pass
            # 回退：扫描所有div，筛选绝对定位且包含中文“发电量”的浮层
            tooltip = self.driver.execute_script(
                r"""
                const cands = Array.from(document.querySelectorAll('div'));
                const hits = [];
                for (const d of cands) {
                  const s = getComputedStyle(d);
                  const t = (d.innerText || '').trim();
                  if (s.position === 'absolute' && (t.includes('发电量') || /\b(kWh|MWh|Wh|度)\b/.test(t))) {
                    hits.push({ t, op: parseFloat(s.opacity||'1'), z: parseInt(s.zIndex||'0',10) || 0 });
                  }
                }
                hits.sort((a,b)=> (b.op - a.op) || (b.z - a.z) || (b.t.length - a.t.length));
                return hits.length ? hits[0].t : '';
                """
            )
            return (tooltip or "").strip()
        except Exception:
            return ""

    def _enter_chart_iframe_if_present(self):
        """尝试切换到包含ECharts canvas的iframe上下文，若成功返回True，否则返回False"""
        try:
            # 先在主文档内检查
            try:
                if self.driver.find_elements(By.CSS_SELECTOR, 'canvas[data-zr-dom-id]'):
                    return True  # 已在正确上下文
            except Exception:
                pass
            frames = self.driver.find_elements(By.TAG_NAME, 'iframe')
            for idx, f in enumerate(frames):
                try:
                    self.driver.switch_to.frame(f)
                    if self.driver.find_elements(By.CSS_SELECTOR, 'canvas[data-zr-dom-id]'):
                        logger.debug(f"已进入包含图表的iframe(index={idx})")
                        return True
                    # 若未找到则返回主文档，继续遍历
                    self.driver.switch_to.default_content()
                except Exception:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass
                    continue
        except Exception:
            pass
        return False

    def _extract_day_from_tooltip_text(self, tip_text):
        """从tooltip文本中提取日期的“日”（1-31），例如"22\n发电量: 2.765MWh" -> 22"""
        if not tip_text:
            return None
        try:
            # 优先匹配独立一行的日数字（常见ECharts tooltip格式）
            m = re.search(r"(?:^|[\r\n])\s*(\d{1,2})\s*(?:[\r\n]|$)", tip_text)
            if m:
                day = int(m.group(1))
                if 1 <= day <= 31:
                    return day
            # 退路1：匹配如"22日"或包含"day"标签的情况
            m2 = re.search(r"(\d{1,2})\s*日", tip_text)
            if m2:
                day = int(m2.group(1))
                if 1 <= day <= 31:
                    return day
            # 退路2：匹配中文日期格式，如"10月22日"
            m3 = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", tip_text)
            if m3:
                day = int(m3.group(2))
                if 1 <= day <= 31:
                    return day
            # 退路3：匹配西文日期，如"2025-10-22"或"10-22"/"10/22"
            m4 = re.search(r"(?:\b\d{4}[-/])?(\d{1,2})[-/](\d{1,2})\b", tip_text)
            if m4:
                day = int(m4.group(2))
                if 1 <= day <= 31:
                    return day
        except Exception:
            pass
        return None

    def _parse_generation_from_text(self, tip_text):
        """从包含“发电量”文本中解析数值，统一返回kWh数值"""
        if not tip_text:
            return None
        m = re.search(r"发电量[：:]\s*([\d.,]+)\s*(kWh|MWh|Wh|度)", tip_text)
        if not m:
            # 宽松匹配：任意位置出现数值+单位
            m = re.search(r"([\d.,]+)\s*(kWh|MWh|Wh|度)", tip_text)
        if not m:
            # 再宽松：若包含“发电/电量”关键词，取文本中最大的数字，视为kWh
            if re.search(r"发电|电量", tip_text):
                nums = re.findall(r"([\d.,]+)", tip_text)
                candidates = []
                for s in nums:
                    s2 = s.replace(',', '').replace('，', '')
                    try:
                        candidates.append(float(s2))
                    except Exception:
                        pass
                if candidates:
                    return round(max(candidates), 2)
            return None
        num_str = m.group(1).replace(',', '').replace('，', '')
        try:
            num = float(num_str)
        except Exception:
            return None
        unit = m.group(2).lower()
        if unit == 'mwh':
            num *= 1000.0
        elif unit == 'wh':
            num /= 1000.0
        # “度”视为kWh
        return round(num, 2)

    def _find_month_chart_canvas(self):
        """在'estation'->'month'页内更稳健地定位月度发电量图表的canvas元素"""
        try:
            # 优先：在包含“发电量”关键字的区域内查找canvas
            xpaths = [

                "//div[contains(., '发电量')]//canvas[@data-zr-dom-id]",
                "//section[contains(., '发电量')]//canvas[@data-zr-dom-id]",
                "//div[contains(@class,'chart') or contains(@class,'curve') or contains(@class,'echarts')]//canvas[@data-zr-dom-id]",
            ]
            for xp in xpaths:
                try:
                    el = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, xp))
                    )
                    if el:
                        try:
                            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                        except Exception:
                            pass
                        return el
                except Exception:
                    pass
            # 回退：页面上第一个canvas[data-zr-dom-id]
            try:
                el = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'canvas[data-zr-dom-id]'))
                )
                if el:
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    except Exception:
                        pass
                    return el
            except Exception:
                pass
        except Exception:
            pass
        return None

    def _fetch_month_value_via_network(self, target_day):
        """通过性能日志与CDP抓取网络JSON，解析目标日发电量(kWh)"""
        try:
            try:
                self.driver.execute_cdp_cmd('Network.enable', {})
            except Exception:
                pass
            time.sleep(0.6)
            try:
                logs = self.driver.get_log('performance')
            except Exception:
                logs = []
            try:
                logger.debug(f"performance logs captured: {len(logs)} entries")
            except Exception:
                pass
            req_ids = []
            urls = {}
            for entry in logs:
                try:
                    data = json.loads(entry.get('message'))
                    method = data.get('message', {}).get('method')
                    params = data.get('message', {}).get('params', {})
                    if method == 'Network.responseReceived':
                        resp = params.get('response', {})
                        mime = (resp.get('mimeType') or '').lower()
                        rtype = (params.get('type') or '').lower()
                        req_id = params.get('requestId')
                        url = resp.get('url')
                        if req_id and ('json' in mime or rtype in ('xhr','fetch')):
                            req_ids.append(req_id)
                            urls[req_id] = url
                except Exception:
                    continue
            try:
                logger.debug(f"candidate response ids: {len(req_ids)}; sample urls: { [urls.get(rid) for rid in req_ids[-3:]] }")
            except Exception:
                pass
            for req_id in reversed(req_ids):
                body_text = None
                try:
                    rb = self.driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': req_id})
                    if rb and isinstance(rb, dict) and 'body' in rb:
                        body_text = rb['body']
                        if rb.get('base64Encoded'):
                            try:
                                body_text = base64.b64decode(body_text).decode('utf-8', errors='ignore')
                            except Exception:
                                pass
                except Exception:
                    continue
                if not body_text:
                    continue
                # 调试：保存最近的响应体以便分析
                try:
                    if isinstance(self.screenshots_dir, str):
                        p = os.path.join(self.screenshots_dir, 'last_network_payload.json')
                        with open(p, 'w', encoding='utf-8') as f:
                            f.write(body_text if isinstance(body_text, str) else str(body_text))
                except Exception:
                    pass
                try:
                    payload = json.loads(body_text)
                except Exception:
                    try:
                        m = re.search(r"\{.*\}", body_text, re.S)
                        payload = json.loads(m.group(0)) if m else None
                    except Exception:
                        payload = None
                if not payload:
                    continue
                try:
                    def pick_label(x):
                        if x is None:
                            return None
                        s = str(x)
                        m2 = re.search(r"(\d{1,2})", s)
                        return int(m2.group(1)) if m2 else None
                    stack = [payload]
                    while stack:
                        cur = stack.pop(0)
                        if isinstance(cur, dict):
                            xa = cur.get('xAxis')
                            se = cur.get('series')
                            if xa and se:
                                xa0 = xa[0] if isinstance(xa, list) else xa
                                xdata = xa0.get('data') if isinstance(xa0, dict) else None
                                if isinstance(xdata, list):
                                    idx = -1
                                    for i, lab in enumerate(xdata):
                                        n = pick_label(lab)
                                        if n is not None and str(n) == str(target_day):
                                            idx = i
                                            break
                                    # 若未找到目标日标签，则不进行回退到最后一条，保持idx为-1，后续将跳过该序列。
                                    if idx < 0:
                                        idx = -1
                                    if isinstance(se, list) and idx >= 0:
                                        for s in se:
                                            data = s.get('data') if isinstance(s, dict) else None
                                            name = str(s.get('name','')) if isinstance(s, dict) else ''
                                            if isinstance(data, list) and len(data) > idx:
                                                item = data[idx]
                                                v = item.get('value') if isinstance(item, dict) else item
                                                if isinstance(v, (int, float)):
                                                    unit = None
                                                    try:
                                                        ya = cur.get('yAxis')
                                                        ya0 = ya[0] if isinstance(ya, list) else ya
                                                        axis_name = str(ya0.get('name','')) if isinstance(ya0, dict) else ''
                                                        if re.search(r"MWh", axis_name, re.I):
                                                            unit = 'MWh'
                                                        elif re.search(r"kWh", axis_name, re.I):
                                                            unit = 'kWh'
                                                    except Exception:
                                                        pass
                                                    num = float(v)
                                                    if unit == 'MWh':
                                                        num *= 1000.0
                                                    return round(num, 2)
                            for v in cur.values():
                                if isinstance(v, (dict, list)):
                                    stack.append(v)
                        elif isinstance(cur, list):
                            for v in cur:
                                if isinstance(v, (dict, list)):
                                    stack.append(v)
                except Exception:
                    continue
            return None
        except Exception:
            return None

    def _hover_day_via_echarts_pixel_map(self, target_day, chart_element=None):
        """使用ECharts的convertToPixel计算目标日柱状图的像素坐标，并执行精准悬停触发tooltip读取"""
        try:
            chart = chart_element or self._find_month_chart_canvas()
            if chart is None:
                chart = WebDriverWait(self.driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'canvas[data-zr-dom-id]'))
                )
            # 获取chart的绝对位置与尺寸
            rect = self.driver.execute_script(
                "const r=arguments[0].getBoundingClientRect(); return {w:r.width,h:r.height,l:r.left,t:r.top};",
                chart
            )
            width = int(rect.get('w') or 0)
            height = int(rect.get('h') or 0)
            left = float(rect.get('l') or 0)
            top = float(rect.get('t') or 0)
            if not width or not height:
                return None
            # 通过JS计算目标日对应的像素坐标
            res = self.driver.execute_script(r"""
            try {
              const chartEl = arguments[0];
              const targetDay = arguments[1];
              const pickLabel = (x) => {
                if (x == null) return null;
                const s = String(x).trim();
                let m;
                // 中文格式：10月27日 / 27日 / 10月27号
                m = s.match(/(?:^|[^0-9])(\d{1,2})\s*(?:日|号)\b/);
                if (m) return parseInt(m[1], 10);
                // 完整日期：YYYY-MM-DD / YYYY/MM/DD / MM-DD / MM/DD / MM.DD
                m = s.match(/(\d{1,4})[\/\.\-](\d{1,2})[\/\.\-](\d{1,2})/);
                if (m) { const d = parseInt(m[3],10); if (d>=1 && d<=31) return d; }
                // 月/日：10/27 或 10-27 或 10.27
                m = s.match(/(\d{1,2})[\/\.\-](\d{1,2})(?![\/\.\-]\d)/);
                if (m) { const d = parseInt(m[2],10); if (d>=1 && d<=31) return d; }
                // 英文或两数字：10 27 或 Oct 27（先捕获第二个数字）
                m = s.match(/\b(\d{1,2})\b[^\d]*\b(\d{1,2})\b/);
                if (m) { const d = parseInt(m[2],10); if (d>=1 && d<=31) return d; }
                // 兜底：单个 1-31 数字
                m = s.match(/\b(\d{1,2})\b/);
                if (m) { const d = parseInt(m[1],10); if (d>=1 && d<=31) return d; }
                return null;
              };
              let inst = null;
              // 先定位容器（而非canvas），优先选择拥有 __echarts__ 的节点
              let container = chartEl;
              try {
                let node = chartEl;
                for (let i=0; i<10 && node; i++) {
                  if (node.__echarts__) { container = node; break; }
                  node = node.parentElement;
                }
              } catch(_){ }
              if (window.echarts && typeof window.echarts.getInstanceByDom==='function' && container) {
                try { inst = window.echarts.getInstanceByDom(container) || null; } catch(_){}
              }
              if (!inst && window.echarts && typeof window.echarts.getInstances==='function') {
                const list = window.echarts.getInstances();
                for (const it of list) {
                  try {
                    const vr = it.getZr().painter.getViewportRoot?.();
                    if (vr && (vr.parentElement === container || container.contains(vr))) { inst = it; break; }
                  } catch(_) {}
                }
              }
              if (!inst) {
                // 如果容器上直接挂了 __echarts__
                try { if (container && container.__echarts__) inst = container.__echarts__; } catch(_){}
              }
              if (!inst) return { ok:false, reason:'no_echarts_instance' };
              let opt = {};
              try { opt = inst.getOption() || {}; } catch(_){}
              const xa = (opt.xAxis && opt.xAxis[0]) ? opt.xAxis[0] : null;
              const xd = xa && xa.data ? xa.data : [];
              let idx = Math.max(0, Math.min((Array.isArray(xd)?xd.length:31)-1, targetDay-1));
              if (Array.isArray(xd)) {
                for (let i=0;i<xd.length;i++){ const n=pickLabel(xd[i]); if (String(n)===String(targetDay)){ idx=i; break; } }
              }
              let px = null;
              try {
                px = inst.convertToPixel({seriesIndex:0}, idx);
                if (Array.isArray(px)) px = px[0];
              } catch(_){ }
              if (px==null) {
                try {
                  const label = Array.isArray(xd) && xd[idx] != null ? xd[idx] : (targetDay);
                  px = inst.convertToPixel({xAxisIndex:0}, label);
                } catch(_){ }
              }
              const r = chartEl.getBoundingClientRect();
              const cx = r.left + (typeof px === 'number' ? px : r.width * ((idx+0.5)/(Math.max(1, (Array.isArray(xd)?xd.length:31)))))
              const cy = r.top + r.height * 0.42;
              return { ok:true, x: Math.round(cx), y: Math.round(cy), idx };
            } catch(e) { return { ok:false, reason:'js_error', error: String(e) } }
            """, chart, int(target_day))
            if not isinstance(res, dict) or not res.get('ok'):
                return None
            abs_x = float(res.get('x'))
            abs_y = float(res.get('y'))
            # 在目标点附近进行微扫（水平±12/±8/±5/±3像素，垂直±6像素），确保命中柱体与触发tooltip
            offsets_x = [-12, -8, -5, -3, 0, 3, 5, 8, 12]
            offsets_y = [-6, 0, 6]
            for dx in offsets_x:
                for dy in offsets_y:
                    try:
                        tx = int(abs_x + dx)
                        ty = int(abs_y + dy)
                        # CDP 鼠标移动到绝对坐标
                        try:
                            self.driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                                'type': 'mouseMoved',
                                'x': tx,
                                'y': ty,
                                'buttons': 0
                            })
                        except Exception:
                            pass
                        # Selenium 相对悬停
                        try:
                            off_x = int(tx - left)
                            off_y = int(ty - top)
                            ActionChains(self.driver).move_to_element_with_offset(chart, off_x, off_y).pause(0.3).perform()
                        except Exception:
                            pass
                        # 进一步：直接通过 ECharts showTip 强制显示指定索引的tooltip
                        try:
                            self.driver.execute_script(
                                r"""
                                try {
                                  const chartEl = arguments[0];
                                  const idx = arguments[1];
                                  let inst = null;
                                  try { if (window.echarts && typeof window.echarts.getInstanceByDom==='function') inst = window.echarts.getInstanceByDom(chartEl) || null; } catch(_){}
                                  if (!inst && window.echarts && typeof window.echarts.getInstances==='function') {
                                    const list = window.echarts.getInstances();
                                    for (const it of list) {
                                      const vr = it.getZr().painter.getViewportRoot?.();
                                      if (vr && (vr.parentElement === chartEl || chartEl.contains(vr))) { inst = it; break; }
                                    }
                                  }
                                  if (!inst && chartEl.__echarts__) inst = chartEl.__echarts__;
                                  if (inst) {
                                    const opt = inst.getOption() || {};
                                    let si = 0;
                                    if (Array.isArray(opt.series)) {
                                      for (let i=0;i<opt.series.length;i++){
                                        const s=opt.series[i];
                                        if (Array.isArray(s.data) && s.data.length>idx) { si=i; break; }
                                      }
                                    }
                                    try { inst.setOption({ tooltip:{ renderMode:'html', trigger:'item', confine:true, enterable:true } }, false); } catch(_){}
                                    try { inst.dispatchAction({ type:'showTip', seriesIndex: si, dataIndex: idx }); } catch(_){}
                                  }
                                } catch(e){}
                                """,
                                chart,
                                int(res.get('idx') or 0)
                            )
                        except Exception:
                            pass
                        # 轮询tooltip
                        tip = None
                        for _ in range(6):
                            time.sleep(0.18)
                            tip = self._collect_tooltip_text()
                            if tip:
                                break
                        day_label = self._extract_day_from_tooltip_text(tip)
                        val = self._parse_generation_from_text(tip)
                        if isinstance(val, (int, float)) and (day_label is not None) and int(day_label) == int(target_day):
                            return round(float(val), 2)
                    except Exception:
                        pass
            return None
        except Exception:
            return None

    def hover_scan_and_read_month_value(self, target_day, chart_element=None):
        """扩展悬停扫描范围并读取ECharts tooltip中的“发电量”数值（包含JS事件触发与可视化调试光标）"""
        try:
            start_time = time.time()
            max_total = 10.0
            chart = chart_element or self._find_month_chart_canvas()
            if chart is None:
                chart = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'canvas[data-zr-dom-id]'))
                )
            # 确保图表进入视口并可交互
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", chart)
                self.driver.execute_script("arguments[0].style.zIndex='10000'; arguments[0].style.pointerEvents='auto';", chart)
            except Exception:
                pass
            # 预检：若页面上没有任何ECharts实例，直接跳过悬停逻辑
            try:
                has_echarts = self.driver.execute_script(
                    r"return !!(window.echarts && typeof window.echarts.getInstances==='function' && window.echarts.getInstances().length>0);"
                )
            except Exception:
                has_echarts = False
            if not has_echarts:
                logger.debug("未检测到window.echarts实例，继续使用事件派发与OCR兜底")
                try:
                    self.driver.execute_script("try{ const c=window.__hover_debug_cursor__; if(c){ c.remove(); window.__hover_debug_cursor__=null; } }catch(e){}")
                except Exception:
                    pass
                # 不提前返回，继续尝试悬停与OCR
            # 注入一个可视化的调试光标（红点），帮助确认悬停坐标是否移动
            try:
                self.driver.execute_script(
                    r"""
                    if (!window.__hover_debug_cursor__) {
                      const c = document.createElement('div');
                      c.id = '__hover_debug_cursor__';
                      c.style.position='fixed';
                      c.style.zIndex='2147483647';
                      c.style.width='10px';
                      c.style.height='10px';
                      c.style.borderRadius='50%';
                      c.style.background='red';
                      c.style.boxShadow='0 0 6px rgba(255,0,0,0.8)';
                      c.style.pointerEvents='none';
                      c.style.opacity='0.75';
                      document.body.appendChild(c);
                      window.__hover_debug_cursor__ = c;
                    }
                    """
                )
            except Exception:
                pass
            # 获取尺寸及位置
            rect = self.driver.execute_script(
                "const r=arguments[0].getBoundingClientRect(); return {w:r.width,h:r.height,l:r.left,t:r.top};",
                chart
            )
            width = int(rect.get('w') or 0)
            height = int(rect.get('h') or 0)
            left = float(rect.get('l') or 0)
            top = float(rect.get('t') or 0)
            if not width or not height:
                return None
            pad_left = max(60, int(width * 0.12))
            pad_right = max(20, int(width * 0.06))
            eff = max(10, int(width - pad_left - pad_right))
            day = max(1, min(31, int(target_day)))
            logger.info(f"hover_scan target_day={day} (now-1) on month view")
            # 先尝试使用像素映射法直接命中目标日
            try:
                val_pix = self._hover_day_via_echarts_pixel_map(day, chart)
                if isinstance(val_pix, (int, float)):
                    return val_pix
            except Exception:
                pass
            offsets = [0, -1, 1, -2, 2, -3, 3, -4, 4, -5, 5, -6, 6, -7, 7]
            y_fracs = [0.42, 0.38, 0.46, 0.35, 0.50]
            tries = []
            for off in offsets:
                if time.time() - start_time > max_total:
                    break
                idx = max(1, min(31, day + off))
                for y_frac in y_fracs:
                    x = pad_left + int(eff * ((idx - 0.5) / 31.0))
                    y = int(height * y_frac)
                    tries.append((x, y, off))
            center_p = max(0.02, min(0.98, ((day - 0.5) / 31.0)))
            for p in [center_p - 0.08, center_p - 0.05, center_p - 0.03, center_p, center_p + 0.03, center_p + 0.05, center_p + 0.08]:
                if p <= 0.0 or p >= 1.0:
                    continue
                x = pad_left + int(eff * p)
                y = int(height * 0.42)
                tries.append((x, y, None))
            # 执行悬停
            for (x, y, off) in tries:
                try:
                    # 将调试光标移动到指定的页面绝对坐标
                    abs_x = left + x
                    abs_y = top + y
                    try:
                        self.driver.execute_script(
                        r"""
                        const cx = arguments[0];
                        const cy = arguments[1];
                        const c = window.__hover_debug_cursor__;
                        if (c) { c.style.left = (cx - 5) + 'px'; c.style.top = (cy - 5) + 'px'; }
                        """,
                        abs_x, abs_y
                    )
                    except Exception:
                        pass
                    # 在每次尝试前，主动隐藏可能粘连的tooltip，避免锁定在旧条目
                    try:
                        self.driver.execute_script(
                            r"""
                            try {
                              if (window.echarts && typeof window.echarts.getInstances==='function') {
                                const list = window.echarts.getInstances();
                                for (const it of list) {
                                  try {
                                    it.dispatchAction({ type:'hideTip' });
                                    it.dispatchAction({ type:'downplay' });
                                  } catch(_) {}
                                }
                              }
                            } catch(e) {}
                            """
                        )
                    except Exception:
                        pass
                    # 0) 通过CDP强制全局鼠标移动到页面绝对坐标，确保触发mousemove
                    try:
                        self.driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                            'type': 'mouseMoved',
                            'x': int(abs_x),
                            'y': int(abs_y),
                            'buttons': 0
                        })
                        logger.debug(f"CDP mouseMoved -> ({int(abs_x)},{int(abs_y)})")
                    except Exception:
                        pass
                    # 1) ActionChains原生悬停
                    ActionChains(self.driver).move_to_element_with_offset(chart, x, y).pause(0.6).perform()
                    time.sleep(0.8)
                    # 调试：保存悬停后的整页截图
                    try:
                        if isinstance(self.screenshots_dir, str):
                            fn = os.path.join(self.screenshots_dir, 'power_curve_6_hover.png')
                            self.driver.save_screenshot(fn)
                    except Exception:
                        pass
                    tip = self._collect_tooltip_text()
                    if tip:
                        logger.debug(f"hover tip: ({x},{y}) -> {tip}")
                    day_label = self._extract_day_from_tooltip_text(tip)
                    val = self._parse_generation_from_text(tip)
                    computed_day = max(1, min(31, int(round((x - pad_left) / float(eff) * 31))))
                    logger.debug(f"parsed day_label={day_label}, computed_day={computed_day}, target={day}")
                    if val is not None and (day_label is not None) and int(day_label) == int(day):
                        return val
                    # 2) JS派发事件到canvas及其容器（包括mouseenter/mouseover/mousemove）
                    self.driver.execute_script(
                        r"""
                        const el = arguments[0];
                        const x = arguments[1];
                        const y = arguments[2];
                        const targetDay = arguments[3];
                        const makeEvt = (type) => new MouseEvent(type, {
                          bubbles: true,
                          cancelable: true,
                          view: window,
                          clientX: x,
                          clientY: y
                        });
                        const evtEnter = makeEvt('mouseenter');
                        const evtOver = makeEvt('mouseover');
                        const evtMove = makeEvt('mousemove');
                        // 派发到canvas本身
                        el.dispatchEvent(evtEnter);
                        el.dispatchEvent(evtOver);
                        el.dispatchEvent(evtMove);
                        // 额外派发PointerEvent以兼容zrender（ECharts绑定pointermove优先）
                        try {
                          const ptr = new PointerEvent('pointermove', { bubbles:true, cancelable:true, pointerType:'mouse', clientX:x, clientY:y, buttons:0 });
                          el.dispatchEvent(ptr);
                        } catch(_){ }
                        // 派发到父容器
                        const parent = el.parentElement || el;
                        parent.dispatchEvent(evtEnter);
                        parent.dispatchEvent(evtOver);
                        parent.dispatchEvent(evtMove);
                        try { parent.dispatchEvent(new PointerEvent('pointermove', { bubbles:true, cancelable:true, pointerType:'mouse', clientX:x, clientY:y, buttons:0 })); } catch(_){}
                        // 派发到该坐标下的真实目标元素（可能是容器或覆盖层）
                        try {
                          const tgt = document.elementFromPoint(x, y);
                          if (tgt) {
                            tgt.dispatchEvent(evtEnter);
                            tgt.dispatchEvent(evtOver);
                            tgt.dispatchEvent(evtMove);
                            try { tgt.dispatchEvent(new PointerEvent('pointermove', { bubbles:true, cancelable:true, pointerType:'mouse', clientX:x, clientY:y, buttons:0 })); } catch(_){}
                          }
                        } catch(e) {}
                        // 尝试定位 ECharts 实例并直接 showTip（即便不依赖真实鼠标）
                        try {
                          let inst = null;
                          if (window.echarts && typeof window.echarts.getInstances === 'function') {
                            const list = window.echarts.getInstances();
                            for (const it of list) {
                              try {
                                const vr = it.getZr().painter.getViewportRoot?.();
                                if (vr && (vr === el || vr === parent)) { inst = it; break; }
                              } catch(_) {}
                            }
                          }
                          if (!inst) {
                            // 向上寻找带有 __echarts__ 的容器
                            let node = el;
                            for (let i=0; i<5 && node; i++) {
                              if (node.__echarts__) { inst = node.__echarts__; break; }
                              node = node.parentElement;
                            }
                          }
                          if (inst) {
                            let opt = {};
                            try { opt = inst.getOption() || {}; } catch(_) {}
                            const xa = (opt.xAxis && opt.xAxis[0]) ? opt.xAxis[0] : null;
                            const xd = xa && xa.data ? xa.data : null;
                            const pickLabel = (x) => {
                              if (x == null) return null;
                              const s = String(x).trim();
                              let m;
                              // 中文格式：10月27日 / 27日 / 10月27号
                              m = s.match(/(?:^|[^0-9])(\d{1,2})\s*(?:日|号)\b/);
                              if (m) return parseInt(m[1], 10);
                              // 完整日期：YYYY-MM-DD / YYYY/MM/DD / MM-DD / MM/DD / MM.DD
                              m = s.match(/(\d{1,4})[\/\.\-](\d{1,2})[\/\.\-](\d{1,2})/);
                              if (m) { const d = parseInt(m[3],10); if (d>=1 && d<=31) return d; }
                              // 月/日：10/27 或 10-27 或 10.27
                              m = s.match(/(\d{1,2})[\/\.\-](\d{1,2})(?![\/\.\-]\d)/);
                              if (m) { const d = parseInt(m[2],10); if (d>=1 && d<=31) return d; }
                              // 英文或两数字：10 27 或 Oct 27（先捕获第二个数字）
                              m = s.match(/\b(\d{1,2})\b[^\d]*\b(\d{1,2})\b/);
                              if (m) { const d = parseInt(m[2],10); if (d>=1 && d<=31) return d; }
                              // 兜底：单个 1-31 数字
                              m = s.match(/\b(\d{1,2})\b/);
                              if (m) { const d = parseInt(m[1],10); if (d>=1 && d<=31) return d; }
                              return null;
                            };
                            let idx = Math.max(0, Math.min((Array.isArray(xd)?xd.length:31)-1, targetDay-1));
                            if (Array.isArray(xd)) {
                              for (let i=0;i<xd.length;i++){ const n=pickLabel(xd[i]); if (String(n)===String(targetDay)){ idx=i; break; } }
                            }
                            let si = 0;
                            if (Array.isArray(opt.series)) {
                              for (let i=0;i<opt.series.length;i++){
                                const s = opt.series[i];
                                if (Array.isArray(s.data) && s.data.length>idx) { si=i; break; }
                              }
                            }
                            try { inst.setOption({ tooltip:{ renderMode:'html', trigger:'item', confine:true, enterable:true } }, false); } catch(_){ }
                            try { inst.dispatchAction({ type:'showTip', seriesIndex: si, dataIndex: idx }); } catch(_){ }
                            try { inst.dispatchAction({ type:'highlight', seriesIndex: si, dataIndex: idx }); } catch(_){ }
                          }
                        } catch(e) {}
                        """,
                        chart, abs_x, abs_y, day
                    )
                    # 轮询等待tooltip出现（最多1.2秒，每200ms检查一次）
                    tip2 = None
                    for _ in range(6):
                        time.sleep(0.20)
                        tip2 = self._collect_tooltip_text()
                        if tip2 or (time.time() - start_time > max_total):
                            break
                    if tip2:
                        logger.debug(f"hover tip2: ({x},{y}) -> {tip2}")
                    day_label2 = self._extract_day_from_tooltip_text(tip2)
                    val2 = self._parse_generation_from_text(tip2)
                    computed_day2 = max(1, min(31, int(round((x - pad_left) / float(eff) * 31))))
                    logger.debug(f"parsed2 day_label={day_label2}, computed_day={computed_day2}, target={day}")
                    if val2 is not None and (day_label2 is not None) and int(day_label2) == int(day):
                        try:
                            self.driver.execute_script("try{ const c=window.__hover_debug_cursor__; if(c){ c.remove(); window.__hover_debug_cursor__=null; } }catch(e){}")
                        except Exception:
                            pass
                        return val2
                except Exception:
                    continue
            # 粗扫：全宽度步进扫描（可选），尽量触发tooltip（限时，步进更大，每步更快）
            coarse_scan_enabled = False
            if coarse_scan_enabled:
                try:
                    for y_frac in [0.42, 0.35, 0.50]:
                        if time.time() - start_time > max_total:
                            break
                        for x in range(pad_left + 5, width - pad_right - 5, 60):
                            if time.time() - start_time > max_total:
                                break
                            try:
                                abs_x = left + x
                                abs_y = top + int(height * y_frac)
                                try:
                                    self.driver.execute_script(
                                        """
                                        const cx = arguments[0];
                                        const cy = arguments[1];
                                        const c = window.__hover_debug_cursor__;
                                        if (c) { c.style.left = (cx - 5) + 'px'; c.style.top = (cy - 5) + 'px'; }
                                        """,
                                        abs_x, abs_y
                                    )
                                except Exception:
                                    pass
                                ActionChains(self.driver).move_to_element_with_offset(chart, x, int(height * y_frac)).pause(0.25).perform()
                                time.sleep(0.35)
                                tip3 = self._collect_tooltip_text()
                                if tip3:
                                    logger.debug(f"hover tip3: ({x},{int(height * y_frac)}) -> {tip3}")
                                day_label3 = self._extract_day_from_tooltip_text(tip3)
                                val3 = self._parse_generation_from_text(tip3)
                                computed_day3 = max(1, min(31, int(round((x - pad_left) / float(eff) * 31))))
                                if val3 is not None and ((day_label3 == day) or (day_label3 is None and computed_day3 == day)):
                                    try:
                                        self.driver.execute_script("try{ const c=window.__hover_debug_cursor__; if(c){ c.remove(); window.__hover_debug_cursor__=null; } }catch(e){}")
                                    except Exception:
                                        pass
                                    return val3
                            except Exception:
                                continue
                except Exception:
                    pass
            # 最后一步：明确将鼠标停留在目标日柱上
            try:
                x_target = pad_left + int(eff * ((day - 0.5) / 31.0))
                y_target = int(height * 0.42)
                abs_x = left + x_target
                abs_y = top + y_target
                try:
                    self.driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                        'type': 'mouseMoved',
                        'x': int(abs_x),
                        'y': int(abs_y),
                        'buttons': 0
                    })
                except Exception:
                    pass
                try:
                    ActionChains(self.driver).move_to_element_with_offset(chart, x_target, y_target).pause(0.4).perform()
                except Exception:
                    pass
                try:
                    self.driver.execute_script(
                        r"""
                        const el = arguments[0];
                        const x = arguments[1];
                        const y = arguments[2];
                        const makeEvt = (type) => new MouseEvent(type, { bubbles:true, cancelable:true, clientX:x, clientY:y });
                        el.dispatchEvent(makeEvt('mouseenter'));
                        el.dispatchEvent(makeEvt('mouseover'));
                        el.dispatchEvent(makeEvt('mousemove'));
                        try { el.dispatchEvent(new PointerEvent('pointermove', { bubbles:true, cancelable:true, clientX:x, clientY:y, buttons:0 })); } catch(_){}
                        """,
                        chart, abs_x, abs_y
                    )
                except Exception:
                    pass
                tip_final = self._collect_tooltip_text()
                if tip_final:
                    day_label_final = self._extract_day_from_tooltip_text(tip_final)
                    val_final = self._parse_generation_from_text(tip_final)
                    logger.debug(f"final hover tip: ({x_target},{y_target}) -> {tip_final}, label={day_label_final}, target={day}")
                    if val_final is not None and (day_label_final is not None) and int(day_label_final) == int(day):
                        return val_final
                    # 若解析到的日号存在但与目标不一致，按差值进行一次纠偏重悬停
                    if day_label_final is not None:
                        try:
                            delta_days = int(day_label_final) - int(day)
                            if delta_days != 0 and abs(delta_days) <= 3:
                                logger.info(f"final hover correction: label={day_label_final}, target={day}, delta={delta_days}")
                                x_target2 = x_target - int(eff * (delta_days / 31.0))
                                abs_x2 = left + x_target2
                                try:
                                    self.driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                                        'type': 'mouseMoved',
                                        'x': int(abs_x2),
                                        'y': int(abs_y),
                                        'buttons': 0
                                    })
                                except Exception:
                                    pass
                                try:
                                    ActionChains(self.driver).move_to_element_with_offset(chart, x_target2, y_target).pause(0.4).perform()
                                except Exception:
                                    pass
                                try:
                                    self.driver.execute_script(
                                        r"""
                                        const el = arguments[0];
                                        const x = arguments[1];
                                        const y = arguments[2];
                                        const makeEvt = (type) => new MouseEvent(type, { bubbles:true, cancelable:true, clientX:x, clientY:y });
                                        el.dispatchEvent(makeEvt('mouseenter'));
                                        el.dispatchEvent(makeEvt('mouseover'));
                                        el.dispatchEvent(makeEvt('mousemove'));
                                        try { el.dispatchEvent(new PointerEvent('pointermove', { bubbles:true, cancelable:true, clientX:x, clientY:y, buttons:0 })); } catch(_){}
                                        """,
                                        chart, abs_x2, abs_y
                                    )
                                except Exception:
                                    pass
                                tip_final2 = self._collect_tooltip_text()
                                if tip_final2:
                                    day_label_final2 = self._extract_day_from_tooltip_text(tip_final2)
                                    val_final2 = self._parse_generation_from_text(tip_final2)
                                    logger.debug(f"final hover tip2: ({x_target2},{y_target}) -> {tip_final2}, label={day_label_final2}, target={day}")
                                    if val_final2 is not None and (day_label_final2 is not None) and int(day_label_final2) == int(day):
                                        return val_final2
                        except Exception:
                            pass
            except Exception:
                pass
            return None
        except Exception:
            return None

    def ocr_read_chart_value_after_hover(self, target_day=None, chart_element=None):
        """精确悬停后进行截图并用OCR解析发电量（优先尝试目标日与邻近日）"""
        if pytesseract is None or Image is None:
            return None
        try:
            chart = chart_element or self._find_month_chart_canvas()
            if chart is None:
                chart = WebDriverWait(self.driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'canvas[data-zr-dom-id]'))
                )
            day = target_day or (datetime.now() - timedelta(days=1)).day
            # 计算大致坐标
            try:
                info = self.driver.execute_script(
                    "const r=arguments[0].getBoundingClientRect(); return {width: Math.floor(r.width), height: Math.floor(r.height), left: Math.floor(r.left), top: Math.floor(r.top)};",
                    chart
                )
                width = int(info.get('width') or 800)
                height = int(info.get('height') or 300)
                left = int(info.get('left') or 0)
                top = int(info.get('top') or 0)
            except Exception:
                width, height = chart.size.get('width', 800), chart.size.get('height', 300)
                left, top = 0, 0
            pad = max(8, int(width * 0.04))
            eff = max(1, width - 2 * pad)
            candidates = [day, day - 1, day + 1, day - 2, day + 2]
            for d in candidates:
                if d < 1 or d > 31:
                    continue
                x = pad + int((d - 0.5) / 31.0 * eff)
                y_frac = 0.40
                try:
                    # 将事件派发到canvas的父容器，提升tooltip触发概率
                    parent = self.driver.execute_script("return arguments[0].parentElement || arguments[0];", chart)
                    pinfo = self.driver.execute_script(
                        "const r=arguments[0].getBoundingClientRect(); return {left: Math.floor(r.left), top: Math.floor(r.top)};",
                        parent
                    )
                    abs_x, abs_y = int(pinfo.get('left', 0)) + x, int(pinfo.get('top', 0)) + int(height * y_frac)
                    # 发送pointer/mouse事件提高悬停稳定性
                    self.driver.execute_script(
                        """
                        try {
                          const el = arguments[0];
                          const px = arguments[1], py = arguments[2];
                          el.dispatchEvent(new PointerEvent('pointermove', {bubbles:true,clientX:px,clientY:py}));
                          el.dispatchEvent(new MouseEvent('mousemove', {bubbles:true,clientX:px,clientY:py}));
                        } catch(e){}
                        """,
                        parent, abs_x, abs_y
                    )
                except Exception:
                    pass
                try:
                    ActionChains(self.driver).move_to_element_with_offset(chart, x, int(height * y_frac)).pause(0.2).perform()
                except Exception:
                    pass
                time.sleep(0.2)
                # 先尝试DOM tooltip文本
                tip = self._collect_tooltip_text()
                if tip:
                    day_label = self._extract_day_from_tooltip_text(tip)
                    val = self._parse_generation_from_text(tip)
                    if val is not None and (day_label is not None) and int(day_label) == int(d):
                        return val
                # 截图并OCR
                hover_path = os.path.join(self.screenshots_dir, 'power_curve_6_hover.png')
                try:
                    png = self.driver.get_screenshot_as_png()
                    img = Image.open(io.BytesIO(png))
                    pad_pix = 60
                    box = (max(0, left - pad_pix), max(0, top - pad_pix), left + width + pad_pix, top + height + pad_pix)
                    crop = img.crop(box)
                    crop.save(hover_path)
                except Exception:
                    # 回退到元素截图
                    try:
                        chart.screenshot(hover_path)
                    except Exception:
                        continue
                try:
                    if hasattr(pytesseract, 'pytesseract'):
                        pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
                except Exception:
                    pass
                txt = ''
                try:
                    txt = pytesseract.image_to_string(Image.open(hover_path), lang='chi_sim+eng')
                except Exception:
                    txt = ''
                txt = (txt or '').strip()
                try:
                    logger.debug(f"OCR文本采样({d}): {txt[:200]}")
                    with open(os.path.join(self.screenshots_dir, 'ocr_text_last.txt'), 'w', encoding='utf-8') as f:
                        f.write(txt)
                except Exception:
                    pass
                day_label = self._extract_day_from_tooltip_text(txt)
                val = self._parse_generation_from_text(txt)
                if val is not None and (day_label is not None) and int(day_label) == int(d):
                    return val
            return None
        except Exception:
            return None

    def perform_post_login_actions(self):
        """执行登录后的操作，只包含点击anticon-caret-left元素和截取canvas图表"""
        try:
            if not self.driver:
                logger.error('WebDriver未初始化，无法执行登录后的操作')
                return False
            
            logger.info('开始执行登录后的操作')
            
            # 用户要求：点击anticon-caret-left元素
            try:
                logger.info('尝试点击class=anticon-caret-left的元素')
                # 尝试点击anticon-caret-left元素
                try:
                    anticon_element = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CLASS_NAME, 'anticon-caret-left'))
                    )
                    anticon_element.click()
                    logger.info('成功点击class=anticon-caret-left的元素')
                    # 等待页面变化
                    time.sleep(2)
                    # 额外等待，确保页面与图表稳定
                    time.sleep(5)
                except Exception as e:
                    logger.error(f'点击class=anticon-caret-left元素失败: {str(e)}')
                
                # 用户要求：截取canvas图表并保存，使用传入的screenshots_dir参数
                try:
                    logger.info('尝试截取canvas[data-zr-dom-id]图表')
                    chart = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'canvas[data-zr-dom-id]'))
                    )
                    # 确保图表元素可见
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", chart)
                    time.sleep(1)
                    # 截取图表并保存到指定路径，命名为power_curve_6.png
                    chart_screenshot_path = os.path.join(self.screenshots_dir, 'power_curve_6.png')
                    chart.screenshot(chart_screenshot_path)
                    logger.info(f'成功截取canvas图表并保存至: {chart_screenshot_path}')
                except Exception as e:
                    logger.error(f'截取canvas图表失败: {str(e)}')
                # 新增：截图完成后，进入“estation”模块并切换“月”标签，提取本日发电量
                try:
                    dg = self.extract_daily_generation_via_station_menu()
                    self.extracted_daily_generation = dg
                    target_date = datetime.now() - timedelta(days=1)
                    target_day = target_date.day
                    logger.info(f"通过estation模块提取到前一日({target_date.strftime('%Y-%m-%d')}, 日={target_day})发电量: {dg}")
                except Exception as nav_e:
                    logger.warning(f"导航至estation/月份页并提取本日发电量失败: {nav_e}")
            except Exception as e:
                logger.error(f'执行用户要求的点击和截图操作时出错: {str(e)}')
            
            logger.info('登录后的操作执行完成')
            return True
        except Exception as e:
            logger.error(f'执行登录后操作时发生错误: {str(e)}')
            
            # 截取错误页面截图用于调试
            try:
                if self.driver:
                    error_screenshot = os.path.join(self.screenshots_dir, f'esolar_post_login_error_{int(time.time())}.png')
                    self.driver.save_screenshot(error_screenshot)
                    logger.info(f'登录后操作错误截图已保存至: {error_screenshot}')
            except:
                pass
            
            return False

    def extract_daily_generation_via_station_menu(self):
        """在截图完成后，点击左侧导航'estation'，点击项目项，再点击'月'标签，并尝试提取前一日发电量数值(kWh)。"""
        if not self.driver:
            raise RuntimeError('WebDriver未初始化')
        wait = WebDriverWait(self.driver, 15)
        # 1) 点击左侧导航中的“电站/estation”模块（兼容中文和英文文案，并确保不在iframe中）
        try:
            self.driver.switch_to.default_content()
        except Exception:
            pass
        menu = None
        # 1.1 首选中文“电站”定位
        try:
            menu_span = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'menu') or contains(@class,'menu-warp')]//span[normalize-space(.)='电站']")))
            try:
                menu = menu_span.find_element(By.XPATH, "./ancestor::div[contains(@class,'menu-warp')][1]")
            except Exception:
                menu = menu_span
        except Exception:
            # 1.2 回退英文“estation”定位（不区分大小写）
            try:
                menu_span = wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'menu') or contains(@class,'menu-warp')]//span[contains(translate(normalize-space(.),'ESTATION','estation'),'estation')]")))
                try:
                    menu = menu_span.find_element(By.XPATH, "./ancestor::div[contains(@class,'menu-warp')][1]")
                except Exception:
                    menu = menu_span
            except Exception:
                # 1.3 最后兜底：点击第一个菜单容器
                try:
                    menu = wait.until(EC.element_to_be_clickable((By.XPATH, "(//div[contains(@class,'menu-warp')])[1]")))
                except Exception:
                    raise RuntimeError("未找到左侧导航的'estation'菜单")
        # 1.4 多策略点击
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", menu)
        except Exception:
            pass
        clicked = False
        try:
            menu.click()
            clicked = True
        except Exception:
            pass
        if not clicked:
            try:
                ActionChains(self.driver).move_to_element(menu).click().perform()
                clicked = True
            except Exception:
                pass
        if not clicked:
            try:
                self.driver.execute_script("arguments[0].click();", menu)
                clicked = True
            except Exception:
                pass
        time.sleep(1)
        # 2) 点击项目项（ant-space-item）。优先点击包含“零碳商业园”的项，否则点击第一个。
        station_item = None
        try:
            station_item = wait.until(EC.element_to_be_clickable((By.XPATH, "(//div[contains(@class,'ant-space-item')])[1]")))
        except Exception:
            station_item = wait.until(EC.element_to_be_clickable((By.XPATH, "(//div[contains(@class,'ant-space-item')])[1]")))
        try:
            self.driver.execute_script("arguments[0].scrollIntoView(true);", station_item)
        except Exception:
            pass
        station_item.click()
        time.sleep(1)
        # 等待页面加载五秒
        logger.info('点击项目项后，等待页面加载五秒')
        time.sleep(5)
        # 3) 点击tab-switch下的“月”标签
        tab_switch = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "tab-switch")))
        # 强化“月”标签的定位与点击策略
        # 1) 先定位“月”元素，如果找不到就按序回退
        month_tab_xpath = ".//div[normalize-space(.)='月']"
        try:
            month_tab = tab_switch.find_element(By.XPATH, month_tab_xpath)
        except Exception:
            candidates = tab_switch.find_elements(By.XPATH, ".//div")
            month_tab = candidates[1] if len(candidates) >= 2 else (candidates[0] if candidates else None)
            if month_tab is None:
                raise RuntimeError("未找到'月'标签")
    
        # 2) 滚动到视口中央
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", month_tab)
        except Exception:
            pass
    
        # 3) 重复点击两次“月”标签以确保切换成功（无论初始是否激活）
        for i in range(2):
            clicked = False
            # 3.1 尝试常规的可点击等待 + 点击
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[@class='tab-switch']/div[normalize-space(.)='月']"))
                ).click()
                clicked = True
            except Exception:
                pass

            # 3.2 尝试ActionChains点击
            if not clicked:
                try:
                    ActionChains(self.driver).move_to_element(month_tab).click().perform()
                    clicked = True
                except Exception:
                    pass

            # 3.3 尝试JS点击
            if not clicked:
                try:
                    self.driver.execute_script("arguments[0].click();", month_tab)
                    clicked = True
                except Exception:
                    pass

            time.sleep(0.6)

        # 4) 等待“月”变为激活态
        try:
            WebDriverWait(self.driver, 8).until(
                lambda d: "active" in d.find_element(By.XPATH, "//div[@class='tab-switch']/div[normalize-space(.)='月']").get_attribute("class")
            )
        except Exception:
            try:
                self.driver.execute_script("arguments[0].classList.add('active');", month_tab)
            except Exception:
                pass
        time.sleep(1)
        # 点击月标签后等待五秒
        logger.info('点击月标签后，等待五秒')
        time.sleep(5)
        # 进入包含图表的iframe（若存在），先回到主文档再递归查找
        try:
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass
            # 优先递归查找，支持多层iframe
            switched = self._switch_to_canvas_context_recursive(max_depth=4)
            if not switched:
                # 回退到旧的单层iframe尝试
                switched = self._enter_chart_iframe_if_present()
            if switched:
                logger.debug("已切换至包含图表的iframe上下文(递归/回退)")
        except Exception as e:
            logger.debug(f"切换iframe上下文失败或无需切换: {e}")
        # 等待月度图表实例就绪（x轴包含至少26个天刻度）
        try:


            WebDriverWait(self.driver, 12).until(
                lambda d: d.execute_script(
                    r"""
                    try {
                      if (!window.echarts || typeof window.echarts.getInstances !== 'function') return false;
                      const insts = window.echarts.getInstances();
                      if (!insts.length) return false;
                      for (const inst of insts) {
                        const opt = inst.getOption() || {};
                        const xa = (opt.xAxis && opt.xAxis[0]) ? opt.xAxis[0] : null;
                        const xData = xa && xa.data ? xa.data : null;
                        if (Array.isArray(xData) && xData.length >= 26 && xData.length <= 31) return true;
                      }
                      return false;
                    } catch(e) { return false; }
                    """
                )
            )
        except Exception:
            logger.debug("等待月度图表实例就绪超时，继续尝试读取")
        # 准备chart与目标日
        try:
            chart = self._find_month_chart_canvas()
            if chart is None:
                chart = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'canvas[data-zr-dom-id]'))
                )
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", chart)
            except Exception:
                pass
        except Exception:
            chart = None
        target_day = (datetime.now() - timedelta(days=1)).day
        # 优先兜底：通过Network日志抓取JSON并解析
        try:
            val_net = self._fetch_month_value_via_network(target_day)
            if isinstance(val_net, (int, float)):
                return round(float(val_net), 2)
        except Exception:
            pass
        # 先尝试：基于ECharts像素映射的精准悬停读取
        try:
            val_pixel = self._hover_day_via_echarts_pixel_map(target_day, chart_element=chart)
            if isinstance(val_pixel, (int, float)):
                return round(float(val_pixel), 2)
        except Exception:
            pass
        # 执行ECharts读取脚本
        echarts_result = None
        try:
             echarts_result = self.driver.execute_script(r"""
             try {
               const chartEl = arguments[0];
               const targetDay = arguments[1];
               function pickLabel(x){
                 if (x==null) return null;
                 let s = String(x);
                 let m = s.match(/(\\d{1,2})/);
                 return m ? parseInt(m[1],10) : null;
               }
               let inst = null;
               // 优先使用容器元素（拥有 __echarts__ 或其祖先）
               let container = chartEl;
               try {
                 let node = chartEl;
                 for (let i=0; i<10 && node; i++) {
                   if (node.__echarts__) { container = node; break; }
                   node = node.parentElement || node.parentNode;
                 }
               } catch(_) {}
               try {
                 if (window.echarts && typeof window.echarts.getInstanceByDom==='function' && container) {
                   inst = window.echarts.getInstanceByDom(container) || null;
                 }
               } catch(e) {}
               if (!inst) {
                 try {
                   if (window.echarts && typeof window.echarts.getInstances==='function') {
                     const list = window.echarts.getInstances();
                     for (const it of list) {
                       const opt = it.getOption() || {};
                       const xa = (opt.xAxis && opt.xAxis[0]) ? opt.xAxis[0] : null;
                       const xd = xa && xa.data ? xa.data : null;
                       const len = xd ? xd.length : 0;
                       let nums = 0;
                       if (xd) { for (const v of xd){ const n = pickLabel(v); if (n>=1 && n<=31) nums++; } }
                       if (len>=26 && len<=31 && nums>=Math.min(24,len)) { inst = it; break; }
                     }
                   }
                 } catch(e) {}
               }
               if (!inst) {
                 try {
                   let node = chartEl;
                   for (let i=0; i<8 && node; i++) {
                     if (node.__echarts__) { inst = node.__echarts__; break; }
                     try {
                       if (window.echarts && typeof window.echarts.getInstanceByDom==='function') {
                         const maybe = window.echarts.getInstanceByDom(node);
                         if (maybe) { inst = maybe; break; }
                       }
                     } catch(_) {}
                     node = node.parentElement || node.parentNode;
                   }
                 } catch(e) {}
               }
               if (!inst) return { ok:false, reason:'no_echarts_instance' };
               let opt = {};
               try { opt = inst.getOption() || {}; } catch(e) {}
               const xa = (opt.xAxis && opt.xAxis[0]) ? opt.xAxis[0] : null;
               const xd = xa && xa.data ? xa.data : null;
               let idx = -1;
               if (Array.isArray(xd)) {
                 for (let i=0;i<xd.length;i++){ const n = pickLabel(xd[i]); if (String(n)===String(targetDay)){ idx=i; break; } }
               }
               if (idx<0) { const len = xd ? xd.length : 30; idx = Math.max(0, Math.min(len-1, targetDay-1)); }
               try { inst.setOption({ tooltip:{ renderMode:'html', trigger:'item' } }, false); } catch(e) {}
               try { inst.dispatchAction({ type:'showTip', seriesIndex:0, dataIndex:idx }); } catch(e) {}
               try { inst.dispatchAction({ type:'highlight', seriesIndex:0, dataIndex:idx }); } catch(e) {}
               let tipText = '';
               let tipEl = document.querySelector('div.echarts-tooltip') || document.querySelector('div.zr-tooltip') || document.querySelector("div[class*='tooltip']");
               if (tipEl){ tipText = (tipEl.innerText||'').trim(); if (!tipText){ const html=(tipEl.innerHTML||'').trim(); if (html) tipText = html.replace(/<br\s*\/?>/ig,'\n').replace(/<[^>]+>/g,'').trim(); } }
               let val=null, unit=null;
               try {
                 const yAxis = (opt.yAxis && opt.yAxis[0]) ? opt.yAxis[0] : null;
                 const s0 = (opt.series && opt.series[0] && opt.series[0].data) ? opt.series[0].data : null;
                 if (Array.isArray(s0) && s0.length>idx){ const item=s0[idx]; val = (item!=null && typeof item==='object') ? (item.value ?? item) : item; const axisName = yAxis && yAxis.name ? String(yAxis.name):''; unit = /MWh/i.test(axisName) ? 'MWh' : (/kWh/i.test(axisName) ? 'kWh' : null); }
               } catch(e) {}
               const labelDay = (Array.isArray(xd) && xd.length>idx) ? pickLabel(xd[idx]) : null;
               return { ok:true, idx, tipText, val, unit, labelDay };
             } catch(err) { return { ok:false, reason:'js_error', error: String(err) } }
             """,
             chart,
             target_day,
         )
        except Exception as e:
            logger.debug(f"执行ECharts读取脚本失败: {e}")
            echarts_result = None

        logger.info(f"ECharts读取返回: {echarts_result}")
        # 尝试解析结果
        if echarts_result and echarts_result.get('ok'):
            tip_text = (echarts_result.get('tipText') or '').strip()
            tip_day = self._extract_day_from_tooltip_text(tip_text)
            if tip_day == target_day and tip_text:
                m_tip = re.search(r"发电量[：:]\s*([\d.,]+)\s*(kWh|MWh|Wh|度)", tip_text)
                if m_tip:
                    num_str = m_tip.group(1).replace(',', '').replace('，', '')
                    num = float(num_str)
                    unit = m_tip.group(2).lower()
                    if unit == 'mwh':
                        num *= 1000.0
                    elif unit == 'wh':
                        num /= 1000.0
                    return round(num, 2)
            # 回退：使用series数据（单位可能为MWh），转换到kWh
            val = echarts_result.get('val')
            label_day = echarts_result.get('labelDay')
            if val is not None and label_day == target_day:
                try:
                    num = float(val)
                    unit_hint = (echarts_result.get('unit') or '').lower()
                    if unit_hint == 'mwh':
                        num *= 1000.0
                    return round(num, 2)
                except Exception:
                    pass
            # 二次回退：更智能的series选择与单位识别
            if val is None:
                try:
                    adv = self.driver.execute_script(r"""
                    try {
                      const chartEl = arguments[0];
                      const targetDay = arguments[1];
                      function pickLabel(x){
                        if (x==null) return null;
                        const s = String(x).trim();
                        let m;
                        m = s.match(/(?:^|[^0-9])(\d{1,2})\s*(?:日|号)\b/);
                        if (m) return parseInt(m[1],10);
                        m = s.match(/(\d{1,4})[\/\.\-](\d{1,2})[\/\.\-](\d{1,2})/);
                        if (m) { const d = parseInt(m[3],10); if (d>=1 && d<=31) return d; }
                        m = s.match(/(\d{1,2})[\/\.\-](\d{1,2})(?![\/\.\-]\d)/);
                        if (m) { const d = parseInt(m[2],10); if (d>=1 && d<=31) return d; }
                        m = s.match(/\b(\d{1,2})\b[^\d]*\b(\d{1,2})\b/);
                        if (m) { const d = parseInt(m[2],10); if (d>=1 && d<=31) return d; }
                        m = s.match(/\b(\d{1,2})\b/);
                        if (m) { const d = parseInt(m[1],10); if (d>=1 && d<=31) return d; }
                        return null;
                      }
                      let inst=null;
                      try { if (window.echarts && typeof window.echarts.getInstanceByDom==='function' && chartEl) inst = window.echarts.getInstanceByDom(chartEl) || null; } catch(e){}
                      if (!inst) { try { if (window.echarts && typeof window.echarts.getInstances==='function') { const list=window.echarts.getInstances(); for(const it of list){ const opt=it.getOption()||{}; const xa=(opt.xAxis&&opt.xAxis[0])?opt.xAxis[0]:null; const xd=xa&&xa.data?xa.data:null; const len=xd?xd.length:0; let nums=0; if(xd){ for(const v of xd){ const n=pickLabel(v); if(n>=1&&n<=31) nums++; } } if (len>=26&&len<=31 && nums>=Math.min(24,len)) { inst=it; break; } } } } catch(e){}
                      if (!inst) return { ok:false, reason:'no_echarts_instance' };
                      const opt = inst.getOption() || {};
                      const xa = (opt.xAxis && opt.xAxis[0]) ? opt.xAxis[0] : null;
                      const xd = xa && xa.data ? xa.data : null;
                      let idx=-1;
                      if (Array.isArray(xd)) {
                        for(let i=0;i<xd.length;i++){ const n=pickLabel(xd[i]); if (String(n)===String(targetDay)){ idx=i; break; } }
                      }
                      if (idx<0) { idx = Math.max(0, Math.min((xd?xd.length:30)-1, targetDay-1)); }
                      let sIndex=-1;
                      if (Array.isArray(opt.series)) {
                        for(let i=0;i<opt.series.length;i++){
                          const s=opt.series[i]; const data=s&&s.data; const nm=(s&&s.name)?String(s.name):'';
                          const looksEnergy=/发电|电量|能量|能源|产出/i.test(nm);
                          if (Array.isArray(data) && data.length>idx) {
                            const item=data[idx]; const v=(item!=null && typeof item==='object') ? (item.value ?? item) : item;
                            if (typeof v==='number') { sIndex=i; if (looksEnergy) break; }
                          }
                        }
                        if (sIndex<0){
                          for(let i=0;i<opt.series.length;i++){
                            const s=opt.series[i]; const data=s&&s.data;
                            if (Array.isArray(data) && data.length>idx){ const item=data[idx]; const v=(item!=null && typeof item==='object') ? (item.value ?? item) : item; if (typeof v==='number'){ sIndex=i; break; } }
                          }
                        }
                      }
                      let val=null, unit=null;
                      if (sIndex>=0){ try { const s=opt.series[sIndex]; const item=s.data[idx]; val=(item!=null && typeof item==='object') ? (item.value ?? item) : item; } catch(e){} }
                      try { const yAxis=(opt.yAxis && opt.yAxis[0]) ? opt.yAxis[0] : null; const axisName = yAxis && yAxis.name ? String(yAxis.name) : ''; unit = /MWh/i.test(axisName)?'MWh':(/kWh/i.test(axisName)?'kWh':null); } catch(e){}
                      const labelDay = (Array.isArray(xd) && xd.length>idx) ? pickLabel(xd[idx]) : null;
                      return { ok:true, idx, seriesIndex:sIndex, val, unit, labelDay };
                    } catch(err) { return { ok:false, reason:'js_error', error:String(err) } }
                    """,
                    chart,
                    target_day,
                    )
                    if adv and adv.get('ok'):
                        val2 = adv.get('val')
                        label_day2 = adv.get('labelDay')
                        if val2 is not None and label_day2 == target_day:
                            try:
                                num2 = float(val2)
                                unit_hint2 = (adv.get('unit') or '').lower()
                                if unit_hint2 == 'mwh':
                                    num2 *= 1000.0
                                return round(num2, 2)
                            except Exception:
                                pass
                except Exception:
                    pass

        # 9) 兜底：悬停扫描尝试直接触发tooltip并解析
        try:
            tg = (datetime.now() - timedelta(days=1)).day
            val_hover = self.hover_scan_and_read_month_value(tg, chart_element=chart)
            if isinstance(val_hover, (int, float)):
                return round(float(val_hover), 2)
        except Exception:
            pass

        # 9.1) OCR兜底：精确悬停后进行OCR解析
        try:
            val_ocr = self.ocr_read_chart_value_after_hover(target_day, chart_element=chart)
            if isinstance(val_ocr, (int, float)):
                return round(float(val_ocr), 2)
        except Exception:
            pass

        # 9.2) 区域DOM扫描：在图表容器附近搜寻数值+单位
        try:
            container = None
            try:
                container = chart.find_element(By.XPATH, './ancestor::*[contains(@class,"echarts") or contains(@class,"card") or contains(@class,"content")][1]')
            except Exception:
                pass
            texts = []
            try:
                node = container or chart
                arr = self.driver.execute_script(
                    """
                    try {
                      const base = arguments[0];
                      const all = base.querySelectorAll('*');
                      const out = [];
                      for (const el of all) {
                        const t = (el.innerText||'').trim();
                        if (t) out.push(t);
                      }
                      return out;
                    } catch(e) { return []; }
                    """,
                    node
                )
                if isinstance(arr, list):
                    texts = arr
            except Exception:
                pass
            month = (datetime.now() - timedelta(days=1)).month
            for t in texts:
                m = re.search(r"([\d.,]+)\s*(kWh|MWh|Wh|度)", t, re.I)
                if m:
                    has_day = re.search(rf"(?:\b|^)\s*{target_day}\s*日|{month}\s*月\s*{target_day}\s*日", t)
                    if not has_day:
                        continue
                    num = float(m.group(1).replace(',', '').replace('，', ''))
                    unit = m.group(2).lower()
                    if unit == 'mwh':
                        num *= 1000.0
                    elif unit == 'wh':
                        num /= 1000.0
                    return round(num, 2)
        except Exception:
            pass

        # 9.3) 页面范围扫描：全页查找包含单位的数值（最后一步前的回退）
        try:
            texts = []
            try:
                arr = self.driver.execute_script(
                    """
                    try {
                      const all = document.querySelectorAll('*');
                      const out = [];
                      for (const el of all) {
                        const t = (el.innerText||'').trim();
                        if (t) out.push(t);
                      }
                      return out;
                    } catch(e) { return []; }
                    """
                )
                if isinstance(arr, list):
                    texts = arr
            except Exception:
                pass
            month = (datetime.now() - timedelta(days=1)).month
            for t in texts:
                m = re.search(r"([\d.,]+)\s*(kWh|MWh|Wh|度)", t, re.I)
                if m:
                    has_day = re.search(rf"(?:\b|^)\s*{target_day}\s*日|{month}\s*月\s*{target_day}\s*日", t)
                    if not has_day:
                        continue
                    num = float(m.group(1).replace(',', '').replace('，', ''))
                    unit = m.group(2).lower()
                    if unit == 'mwh':
                        num *= 1000.0
                    elif unit == 'wh':
                        num /= 1000.0
                    return round(num, 2)
        except Exception:
            pass

        # 10) 最终兜底：扫描DOM文本块关键词（昨日/昨天/上一日/前一日/上一天）
        try:
            blocks = self.driver.find_elements(By.XPATH, "//*[contains(text(),'昨日') or contains(text(),'昨天') or contains(text(),'上一日') or contains(text(),'前一日') or contains(text(),'上一天')]")
            month = (datetime.now() - timedelta(days=1)).month
            day_pat = re.compile(rf"(?:\\b|^)\\s*{target_day}\\s*日|{month}\\s*月\\s*{target_day}\\s*日")
            for b in blocks:
                txt = (b.text or '').strip()
                if not day_pat.search(txt):
                    continue
                m = re.search(r"([\d.,]+)\s*(kWh|MWh|Wh|度)", txt, re.I)
                if m:
                    num = float(m.group(1).replace(',', '').replace('，', ''))
                    unit = m.group(2).lower()
                    if unit == 'mwh':
                        num *= 1000.0
                    elif unit == 'wh':
                        num /= 1000.0
                    return round(num, 2)
        except Exception:
            pass

        return None


def run_scraper():
    """运行ESolar系统爬虫并返回提取的项目数据"""
    try:
        # 用户信息
        USERNAME = "18663070009"
        PASSWORD = "Aa18663070009"
        
        with ESolarScraper(USERNAME, PASSWORD) as scraper:
            # 执行登录
            login_success = scraper.login()
            
            if login_success:
                logger.info('ESolar系统登录成功，准备执行登录后的操作')
                print('ESolar系统登录成功，准备执行登录后的操作')
                
                # 执行登录后的操作
                post_login_success = scraper.perform_post_login_actions()
                
                if post_login_success:
                    logger.info('ESolar系统登录后的操作执行成功')
                    print('ESolar系统登录后的操作执行成功')
                else:
                    logger.warning('ESolar系统登录后的操作执行失败，但登录本身是成功的')
                    print('ESolar系统登录后的操作执行失败，但登录本身是成功的')
                
                logger.info('ESolar系统登录任务完成')
                # 组装并返回项目数据（仅项目6），同时写入solar_data.json
                dg = getattr(scraper, 'extracted_daily_generation', None)
                result = {
                    "6": {
                        "name": scraper.project_names.get(6),
                        "dcCapacity": scraper.project_capacities.get(6, {}).get("dcCapacity"),
                        "acCapacity": scraper.project_capacities.get(6, {}).get("acCapacity"),
                        "dailyGeneration": dg
                    }
                }
                try:
                    # 读取已存在数据并仅更新项目6的dailyGeneration
                    if os.path.exists(scraper.data_file_path):
                        with open(scraper.data_file_path, 'r', encoding='utf-8') as f:
                            existing = json.load(f)
                    else:
                        existing = {}
                    if isinstance(existing, dict):
                        if "6" in existing:
                            existing["6"]["dailyGeneration"] = dg
                        else:
                            existing["6"] = result["6"]
                    else:
                        existing = result
                    with open(scraper.data_file_path, 'w', encoding='utf-8') as f:
                        json.dump(existing, f, ensure_ascii=False, indent=2)
                    logger.info(f"已更新数据文件: {scraper.data_file_path}")
                except Exception as fe:
                    logger.warning(f"更新数据文件时发生异常: {fe}")
                return result
            else:
                logger.error('ESolar系统登录任务失败')
                print('ESolar系统登录任务失败')
                return {}
    except Exception as e:
        logger.error(f'运行ESolar系统爬虫时出错: {str(e)}')
        print(f'运行ESolar系统爬虫时出错: {str(e)}')
        return {}


if __name__ == "__main__":
    data = run_scraper()
    if data:
        print(f"成功提取项目数据: {data}")
    else:
        print("未提取到项目数据")