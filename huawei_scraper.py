import os
import time
from datetime import datetime
import logging
import ssl
import platform
import subprocess
import sys
import io
from PIL import Image
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager
import urllib3

# 禁用SSL验证警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def is_ci_environment():
    """检测是否在CI环境中运行"""
    return (
        os.getenv('CI') == 'true' or 
        os.getenv('GITHUB_ACTIONS') == 'true' or
        os.getenv('CONTINUOUS_INTEGRATION') == 'true' or
        os.getenv('RUNNER_DEBUG') is not None
    )

class HuaweiFusionSolarScraper:
    def __init__(self, username, password, projects, screenshots_dir='screenshots', headless=False, retry_attempts=3):
        """初始化爬虫"""
        self.username = username
        self.password = password
        self.projects = projects  # 项目列表，格式: [{'name': '项目名称', 'id': '项目ID'}]
        self.screenshots_dir = screenshots_dir
        self.driver = None
        self.headless = headless  # 默认设为False以便调试
        self.retry_attempts = retry_attempts
        
        # 确保截图目录存在
        os.makedirs(self.screenshots_dir, exist_ok=True)
        
        # 检测CI环境
        ci_env = is_ci_environment()
        
        # 根据环境选择浏览器类型
        self.browser_type = 'chrome' if ci_env else 'edge'
        logger.info(f"检测到{'CI' if ci_env else '本地'}环境，将使用{self.browser_type}浏览器")
        
        # 配置浏览器选项
        if self.browser_type == 'chrome':
            self.chrome_options = ChromeOptions()
            
            # CI环境配置
            if ci_env or self.headless:
                logger.info("启用无头模式")
                self.chrome_options.add_argument('--headless')
                self.chrome_options.add_argument('--no-sandbox')
                self.chrome_options.add_argument('--disable-dev-shm-usage')
                self.chrome_options.add_argument('--disable-gpu')
                self.chrome_options.add_argument('--remote-debugging-port=9222')
            
            # 基本配置
            self.chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            self.chrome_options.add_argument('--disable-extensions')
            self.chrome_options.add_argument('--disable-notifications')
            self.chrome_options.add_argument('--window-size=1920,1080')
            
            # SSL相关配置
            self.chrome_options.add_argument('--ignore-certificate-errors')
            self.chrome_options.add_argument('--allow-insecure-localhost')
            self.chrome_options.add_argument('--ssl-protocol=any')
            self.chrome_options.add_argument('--disable-web-security')
            
            # 用户代理
            self.chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
            
            # 实验性选项
            self.chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
            self.chrome_options.add_experimental_option('useAutomationExtension', False)
            
        else:  # Edge
            self.edge_options = EdgeOptions()
            
            # 无头模式配置
            if self.headless:
                logger.info("启用无头模式")
                self.edge_options.add_argument('--headless')
                self.edge_options.add_argument('--window-size=1920,1080')
            
            # 基本配置
            self.edge_options.add_argument('--disable-gpu')
            self.edge_options.add_argument('--no-sandbox')
            self.edge_options.add_argument('--disable-dev-shm-usage')
            self.edge_options.add_argument('--window-size=1920,1080')
            
            # SSL相关配置
            self.edge_options.add_argument('--ignore-certificate-errors')
            self.edge_options.add_argument('--allow-insecure-localhost')
            self.edge_options.add_argument('--ssl-protocol=any')
            self.edge_options.add_argument('--disable-web-security')
            
            # 禁用自动化控制特征
            self.edge_options.add_argument('--disable-blink-features=AutomationControlled')
            
            # 增加用户代理，使用与当前浏览器匹配的UA
            self.edge_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0')
            
            # 实验性选项
            self.edge_options.add_experimental_option('excludeSwitches', ['enable-automation'])
            self.edge_options.add_experimental_option('useAutomationExtension', False)
        
        # 配置日志
        self.setup_logging()
        
        # 检查系统环境
        self.log_system_info()
        
    def setup_logging(self):
        """配置详细日志"""
        # 已经在文件开头配置了基本日志，这里可以添加更详细的日志配置
        pass
    
    def log_system_info(self):
        """记录系统和环境信息"""
        logger.info(f"操作系统: {platform.system()} {platform.version()}")
        logger.info(f"Python版本: {platform.python_version()}")
        
        # 尝试获取Edge浏览器版本
        try:
            if platform.system() == 'Windows':
                # Windows系统下获取Edge版本
                cmd = r'reg query "HKEY_CURRENT_USER\Software\Microsoft\Edge\BLBeacon" /v version'
                result = subprocess.check_output(cmd, shell=True, text=True)
                for line in result.split('\n'):
                    if 'version' in line.lower():
                        edge_version = line.split(':')[-1].strip()
                        logger.info(f"Edge浏览器版本: {edge_version}")
                        break
        except Exception as e:
            logger.warning(f"无法获取Edge浏览器版本: {str(e)}")
    
    def __enter__(self):
        """启动浏览器"""
        attempt = 0
        max_attempts = self.retry_attempts
        
        while attempt < max_attempts:
            try:
                attempt += 1
                logger.info(f"第 {attempt}/{max_attempts} 次尝试启动浏览器...")
                
                if self.browser_type == 'chrome':
                    logger.info("初始化Chrome浏览器...")
                    
                    # 在CI环境中使用webdriver-manager自动管理ChromeDriver
                    if is_ci_environment():
                        logger.info("CI环境：使用webdriver-manager自动管理ChromeDriver")
                        service = ChromeService(ChromeDriverManager().install())
                    else:
                        # 本地环境，尝试使用系统PATH中的ChromeDriver
                        try:
                            service = ChromeService()
                            logger.info("使用系统PATH中的ChromeDriver")
                        except Exception as e:
                            logger.warning(f"系统PATH中的ChromeDriver不可用: {e}")
                            logger.info("回退到webdriver-manager")
                            service = ChromeService(ChromeDriverManager().install())
                    
                    # 初始化Chrome WebDriver
                    self.driver = webdriver.Chrome(
                        service=service,
                        options=self.chrome_options
                    )
                    
                else:  # Edge
                    logger.info("初始化Edge浏览器...")
                    
                    # 尝试使用本地的msedgedriver.exe，但在不存在时回退到系统PATH中的驱动
                    driver_path = os.path.join(os.getcwd(), 'msedgedriver.exe')
                    service = None
                    
                    # 检查驱动是否存在
                    if os.path.exists(driver_path):
                        logger.info(f"使用Edge驱动路径: {driver_path}")
                        # 创建服务对象并配置
                        service = EdgeService(
                            driver_path,
                            log_output=os.path.join(os.getcwd(), 'msedgedriver.log')  # 启用驱动日志
                        )
                    else:
                        logger.info("未找到本地Edge驱动，将使用系统PATH中的驱动")
                        # 不指定驱动路径，让Selenium自动查找系统PATH中的驱动
                        service = EdgeService(log_output=os.path.join(os.getcwd(), 'msedgedriver.log'))
                    
                    # 设置服务日志级别
                    service.log_level = 'INFO'
                    
                    # 初始化WebDriver
                    self.driver = webdriver.Edge(
                        service=service,
                        options=self.edge_options
                    )
                
                # 设置页面加载超时
                self.driver.set_page_load_timeout(60)
                # 设置脚本超时
                self.driver.set_script_timeout(60)
                # 设置隐式等待时间
                self.driver.implicitly_wait(15)
                
                logger.info(f"{self.browser_type}浏览器初始化成功")
                
                # 设置额外的执行环境
                self.driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
                )
                
                return self
            except Exception as e:
                logger.error(f"浏览器启动失败 (尝试 {attempt}/{max_attempts}): {str(e)}")
                
                # 如果是最后一次尝试，抛出异常
                if attempt >= max_attempts:
                    logger.error("达到最大尝试次数，浏览器启动失败")
                    raise
                
                # 否则等待一段时间后重试
                wait_time = 2 * attempt  # 递增等待时间
                logger.info(f"{wait_time}秒后重试...")
                time.sleep(wait_time)
    
    def ensure_driver_alive(self):
        """确保驱动会话仍然有效"""
        if not self.driver:
            logger.error("驱动未初始化")
            return False
            
        try:
            # 尝试获取当前URL来检查会话是否有效
            self.driver.current_url
            return True
        except Exception as e:
            logger.error(f"驱动会话无效: {str(e)}")
            return False
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """关闭浏览器"""
        if self.driver:
            self.driver.quit()
    
    def login(self):
        """登录华为FusionSolar网站"""
        attempt = 0
        max_attempts = self.retry_attempts
        
        while attempt < max_attempts:
            try:
                attempt += 1
                logger.info(f"第 {attempt}/{max_attempts} 次尝试登录华为FusionSolar网站...")
                
                # 确保驱动会话有效
                if not self.ensure_driver_alive():
                    logger.error("驱动会话无效，无法执行登录")
                    return False
                
                # 访问登录页面 - 尝试多种URL
                login_urls = [
                    'https://intl.fusionsolar.huawei.com',
                    'https://uni01cn.fusionsolar.huawei.com/uniportal/pvmswebsite/assets/build/cloud.html?app-id=smartpvms&instance-id=smartpvms',
                    'https://uni01cn.fusionsolar.huawei.com',
                    'https://fusionsolar.huawei.com'
                ]
                
                login_url = None
                for url in login_urls:
                    try:
                        logger.info(f"尝试访问登录页面: {url}")
                        self.driver.get(url)
                        logger.info(f"登录页面请求已发送: {url}")
                        login_url = url
                        break  # 如果成功访问，跳出循环
                    except Exception as url_e:
                        logger.error(f"访问登录页面 {url} 失败: {str(url_e)}")
                        # 短暂等待后尝试下一个URL
                        time.sleep(2)
                
                if not login_url:
                    logger.error("所有登录URL都无法访问")
                    return False
                
                # 等待登录页面加载完成
                logger.info("等待页面加载完成...")
                time.sleep(10)  # 增加等待时间确保完全加载
                
                # 打印当前页面标题和URL用于调试
                try:
                    logger.debug(f"当前页面标题: {self.driver.title}")
                    logger.debug(f"当前页面URL: {self.driver.current_url}")
                except:
                    logger.warning("无法获取页面标题和URL")
                
                # 尝试查找登录元素的多种策略 - 优化版
                try:
                    # 1. 策略一：查找华为登录页面特有的登录容器ID
                    login_container = None
                    login_container_found = False
                    
                    # 首先尝试查找华为登录页面特有的容器ID
                    container_ids = ['loginFormArea', 'loginControl', 'loginWrapper', 'login']
                    for container_id in container_ids:
                        try:
                            logger.info(f"尝试查找华为专用容器ID: {container_id}")
                            login_container = WebDriverWait(self.driver, 15).until(
                                EC.presence_of_element_located((By.ID, container_id))
                            )
                            logger.info(f"成功找到华为专用容器: {container_id}")
                            login_container_found = True
                            break
                        except Exception as container_e:
                            logger.warning(f"未找到容器ID {container_id}: {str(container_e)}")
                    
                    # 2. 策略二：查找所有form元素
                    if not login_container_found:
                        logger.info("尝试策略二：查找所有form元素")
                        try:
                            forms = WebDriverWait(self.driver, 15).until(
                                EC.presence_of_all_elements_located((By.TAG_NAME, 'form'))
                            )
                            if forms:
                                login_container = forms[0]  # 假设第一个form是登录表单
                                logger.info(f"成功找到{len(forms)}个表单，使用第一个作为登录容器")
                                login_container_found = True
                            else:
                                logger.warning("未找到表单元素")
                        except:
                            logger.warning("查找表单元素失败")
                    
                    # 3. 策略三：查找特定class的容器
                    if not login_container_found:
                        logger.info("尝试策略三：查找特定class的容器")
                        try:
                            # 查找包含loginFormArea的容器
                            login_container = WebDriverWait(self.driver, 15).until(
                                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'loginWrapper')]"))
                            )
                            logger.info("成功找到特定class的容器")
                            login_container_found = True
                        except:
                            logger.warning("查找特定class的容器失败")
                    
                    # 4. 最后使用body作为容器
                    if not login_container_found:
                        logger.warning("所有容器查找策略都失败，使用body作为最后的容器选择")
                        login_container = self.driver.find_element(By.TAG_NAME, 'body')
                except Exception as e:
                    logger.error(f"登录容器查找失败: {str(e)}")
                    # 如果不是最后一次尝试，继续
                    if attempt < max_attempts:
                        logger.info(f"{2*attempt}秒后重试登录...")
                        time.sleep(2*attempt)
                        continue
                    return False
                
                # 查找所有input元素
                logger.info("查找页面上的所有input元素...")
                inputs = []
                try:
                    inputs = WebDriverWait(login_container, 15).until(
                        EC.presence_of_all_elements_located((By.TAG_NAME, 'input'))
                    )
                    logger.info(f"找到{len(inputs)}个input元素")
                    
                    # 打印所有input元素的属性用于调试
                    for i, input_elem in enumerate(inputs):
                        try:
                            input_type = input_elem.get_attribute('type')
                            input_id = input_elem.get_attribute('id')
                            input_name = input_elem.get_attribute('name')
                            logger.debug(f"Input {i}: type={input_type}, id={input_id}, name={input_name}")
                        except:
                            continue
                except Exception as input_e:
                    logger.error(f"查找input元素失败: {str(input_e)}")
                    
                # 查找用户名和密码输入框的多种策略
                username_input = None
                password_input = None
                
                # 根据用户提供的华为登录页面HTML结构，优化查找策略
                logger.info("优化版: 优先通过特定ID查找用户名和密码输入框")
                
                # 策略1: 优先查找华为登录页面特有的ID
                try:
                    # 用户名输入框 - ID为'username'
                    username_input = self.driver.find_element(By.ID, 'username')
                    logger.info("找到用户名输入框(ID=username)")
                except Exception as e:
                    logger.warning(f"未找到ID为'username'的输入框: {str(e)}")
                
                try:
                    # 密码输入框 - ID为'value'
                    password_input = self.driver.find_element(By.ID, 'value')
                    logger.info("找到密码输入框(ID=value)")
                except Exception as e:
                    logger.warning(f"未找到ID为'value'的输入框: {str(e)}")
                
                # 策略2: 通过type属性查找
                if not username_input or not password_input:
                    logger.info("策略2: 通过type属性查找用户名和密码输入框")
                    for input_elem in inputs:
                        try:
                            input_type = input_elem.get_attribute('type')
                            if input_type == 'text' and not username_input:
                                username_input = input_elem
                                logger.info("找到用户名输入框(type=text)")
                            elif input_type == 'password' and not password_input:
                                password_input = input_elem
                                logger.info("找到密码输入框(type=password)")
                        except:
                            continue
                
                # 策略3: 通过name属性查找
                if not username_input:
                    logger.info("策略3: 通过name属性查找用户名输入框")
                    for input_elem in inputs:
                        try:
                            name = input_elem.get_attribute('name')
                            if name and ('user' in name.lower() or 'name' in name.lower()):
                                username_input = input_elem
                                logger.info(f"找到用户名输入框(name={name})")
                                break
                        except:
                            continue
                
                if not password_input:
                    logger.info("策略3: 通过name属性查找密码输入框")
                    for input_elem in inputs:
                        try:
                            name = input_elem.get_attribute('name')
                            if name and 'pass' in name.lower():
                                password_input = input_elem
                                logger.info(f"找到密码输入框(name={name})")
                                break
                        except:
                            continue
                
                # 策略4: 通过特定CSS选择器查找
                if not username_input:
                    logger.info("策略4: 使用华为专用CSS选择器查找用户名输入框")
                    try:
                        # 查找登录表单区域内的文本输入框
                        username_input = login_container.find_element(By.CSS_SELECTOR, '#loginFormArea input[type="text"]')
                        logger.info("通过华为专用CSS选择器找到用户名输入框")
                    except:
                        logger.warning("所有用户名输入框查找策略都失败")
                
                if not password_input:
                    logger.info("策略4: 使用华为专用CSS选择器查找密码输入框")
                    try:
                        # 查找登录表单区域内的密码输入框
                        password_input = login_container.find_element(By.CSS_SELECTOR, '#loginFormArea input[type="password"]')
                        logger.info("通过华为专用CSS选择器找到密码输入框")
                    except:
                        logger.warning("所有密码输入框查找策略都失败")
                
                # 如果找到了输入框，输入用户名和密码
                if username_input and password_input:
                    try:
                        logger.info(f"准备输入用户名")
                        username_input.clear()
                        username_input.send_keys(self.username)
                        logger.info("用户名输入成功")
                        
                        password_input.clear()
                        password_input.send_keys(self.password)
                        logger.info("密码输入成功")
                    except Exception as send_e:
                        logger.error(f"输入用户名/密码失败: {str(send_e)}")
                        # 尝试使用JavaScript设置值
                        logger.info("尝试使用JavaScript设置用户名和密码")
                        self.driver.execute_script(f"arguments[0].value='{self.username}';", username_input)
                        self.driver.execute_script(f"arguments[0].value='{self.password}';", password_input)
                else:
                    logger.error("未能找到用户名和密码输入框，登录失败")
                    # 保存页面截图用于调试
                    screenshot_path = os.path.join(self.screenshots_dir, "login_page_debug.png")
                    self.driver.save_screenshot(screenshot_path)
                    logger.info(f"已保存登录页面截图到: {screenshot_path}")
                    
                    # 如果不是最后一次尝试，继续
                    if attempt < max_attempts:
                        logger.info(f"{2*attempt}秒后重试登录...")
                        time.sleep(2*attempt)
                        continue
                    return False
                
                # 检查验证码输入框（如果存在）
                logger.info("检查是否存在验证码输入框...")
                try:
                    captcha_input = None
                    # 尝试多种方式查找验证码输入框
                    for input_elem in inputs:
                        try:
                            input_name = input_elem.get_attribute('name')
                            input_id = input_elem.get_attribute('id')
                            if input_name and 'captcha' in input_name.lower() or input_id and 'captcha' in input_id.lower() or input_name and 'verification' in input_name.lower() or input_id and 'verification' in input_id.lower():
                                captcha_input = input_elem
                                break
                        except:
                            continue
                    
                    if captcha_input and captcha_input.is_displayed():
                        logger.info("检测到验证码输入框")
                        captcha_code = input("请输入网页上的验证码: ")
                        captcha_input.send_keys(captcha_code)
                        logger.info("验证码输入成功")
                except Exception as captcha_e:
                    logger.info(f"未检测到验证码输入框或验证码处理失败: {str(captcha_e)}")
                
                # 查找并点击登录按钮
                logger.info("查找登录按钮...")
                login_button = None
                
                # 策略列表 - 华为登录页面专用版（极简版）
                # 根据用户反馈，只保留核心策略和后备策略3，其他策略不生效
                strategies = [
                    # 基于华为登录页面特定结构的核心策略 - 优先使用
                    {"name": "核心策略: 查找特定ID的密码输入框后的按钮", "by": By.XPATH, "value": "//input[@id='value']/following::*[self::button or self::input[@type='submit'] or self::input[@type='button']][1]"},
                    
                    # 保留后备策略3，根据用户反馈这是唯一生效的后备策略
                    {"name": "后备策略3: 通过文本内容查找", "by": By.XPATH, "value": "//*[contains(text(), '登录')]"}
                ]
                
                # 尝试所有策略
                for strategy in strategies:
                    try:
                        logger.info(strategy["name"])
                        
                        # 普通查找策略
                        elements = self.driver.find_elements(strategy["by"], strategy["value"])
                        if elements:
                            # 选择第一个可见的元素
                            for elem in elements:
                                try:
                                    if elem.is_displayed() and elem.is_enabled():
                                        login_button = elem
                                        logger.info(f"{strategy['name']}找到登录按钮")
                                        break
                                except:
                                    continue
                        
                        if login_button:
                            break
                    except Exception as e:
                        logger.warning(f"{strategy['name']}失败: {str(e)}")
                        continue
                
                # 额外策略：如果上述所有策略都失败，尝试查找页面上的所有可点击元素
                if not login_button:
                    logger.info("尝试终极策略：查找页面上的所有可点击元素")
                    try:
                        clickable_elements = self.driver.find_elements(By.CSS_SELECTOR, '[onclick], [href], button, a')
                        logger.info(f"找到{len(clickable_elements)}个可点击元素")
                        
                        # 选择一个最可能是登录按钮的元素（比如位置在表单附近或最后一个可点击元素）
                        if clickable_elements:
                            # 首先尝试最后几个元素，因为登录按钮通常在表单底部
                            for i in range(-1, -min(5, len(clickable_elements))-1, -1):
                                elem = clickable_elements[i]
                                try:
                                    if elem.is_displayed():
                                        login_button = elem
                                        logger.info(f"选择第{i}个可点击元素作为登录按钮（位置策略）")
                                        break
                                except:
                                    continue
                    except Exception as e:
                        logger.warning(f"终极策略失败: {str(e)}")
                
                # 如果找到了登录按钮，点击它
                if login_button:
                    logger.info("准备点击登录按钮...")
                    try:
                        # 确保登录按钮可点击
                        WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(login_button))
                        login_button.click()
                        logger.info("登录按钮点击成功")
                    except Exception as click_e:
                        logger.error(f"点击登录按钮失败: {str(click_e)}")
                        # 尝试使用JavaScript点击
                        logger.info("尝试使用JavaScript点击登录按钮")
                        self.driver.execute_script("arguments[0].click();", login_button)
                else:
                    logger.error("未能找到登录按钮，登录失败")
                    # 如果不是最后一次尝试，继续
                    if attempt < max_attempts:
                        logger.info(f"{2*attempt}秒后重试登录...")
                        time.sleep(2*attempt)
                        continue
                    return False
                
                # 等待登录成功并跳转到主页
                logger.info("等待登录响应...")
                time.sleep(15)  # 增加等待时间
                
                # 检查是否登录成功
                current_url = None
                try:
                    current_url = self.driver.current_url
                    logger.debug(f"登录后URL: {current_url}")
                except:
                    logger.warning("无法获取当前URL")
                
                # 保存登录后的页面截图用于调试
                after_login_screenshot = os.path.join(self.screenshots_dir, "after_login_debug.png")
                self.driver.save_screenshot(after_login_screenshot)
                logger.info(f"已保存登录后页面截图到: {after_login_screenshot}")
                
                # 检查是否登录成功的多种方法
                success = False
                if current_url and 'login' not in current_url.lower():
                    success = True
                try:
                    if self.driver.title and self.driver.title != "登录":
                        success = True
                except:
                    pass
                
                if success:
                    logger.info("登录成功！")
                    return True
                else:
                    logger.warning("登录可能未成功，URL中仍包含'login'或标题未变化")
                    
                    # 检查是否有登录失败的提示信息
                    try:
                        error_messages = self.driver.find_elements(By.CSS_SELECTOR, '.error-message, .alert-error, .message-error')
                        if error_messages:
                            for error_msg in error_messages:
                                if error_msg.is_displayed():
                                    logger.error(f"登录失败提示: {error_msg.text}")
                    except:
                        pass
                    
                    # 如果不是最后一次尝试，继续
                    if attempt < max_attempts:
                        logger.info(f"{2*attempt}秒后重试登录...")
                        time.sleep(2*attempt)
                        continue
                    return False
            except Exception as e:
                logger.error(f"登录过程中出现错误: {str(e)}")
                # 尝试滚动页面并再次查找元素
                logger.info("尝试滚动页面并重新查找元素...")
                try:
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(3)
                except:
                    pass
                
                # 保存错误页面截图
                error_screenshot = os.path.join(self.screenshots_dir, "login_error.png")
                try:
                    self.driver.save_screenshot(error_screenshot)
                    logger.info(f"已保存登录错误页面截图到: {error_screenshot}")
                except:
                    logger.warning("无法保存错误页面截图")
                
                # 如果不是最后一次尝试，继续
                if attempt < max_attempts:
                    logger.info(f"{2*attempt}秒后重试登录...")
                    time.sleep(2*attempt)
                    continue
                return False
        # 所有尝试都失败
        logger.error("所有登录尝试都失败")
        return False
    
    def navigate_to_project(self, project_name):
        """导航到指定项目"""
        try:
            logger.info(f"导航到项目: {project_name}")
            
            # 项目名称映射字典 - 根据华为网站实际项目名称映射
            project_name_mapping = {
                '滨北南邱': '滨北南邱家村',
                '水立方': '新鼎水立方',
                '宋滩': '新鼎宋滩电站',
                '李赞皇': '新鼎李赞皇光伏电站'
            }
            
            # 获取映射后的项目名称
            mapped_project_name = project_name_mapping.get(project_name, project_name)
            if mapped_project_name != project_name:
                logger.info(f"映射项目名称: {project_name} -> {mapped_project_name}")
            
            # 等待项目列表加载
            time.sleep(8)  # 增加等待时间
            
            # 记录当前页面状态用于调试
            try:
                current_url = self.driver.current_url
                current_title = self.driver.title
                logger.debug(f"当前页面: URL={current_url}, 标题={current_title}")
            except Exception as e:
                logger.warning(f"无法获取当前页面信息: {str(e)}")
            
            # 增强的项目查找策略
            # 对宋滩项目的特殊处理
            if project_name == "宋滩":
                logger.info("针对宋滩项目的特殊处理：直接查找新鼎宋滩电站")
                # 直接使用策略3查找新鼎宋滩电站
                try:
                    # 查找包含'新鼎宋滩电站'文本的元素
                    specific_xpath = "//*[contains(text(), '新鼎宋滩电站')]"
                    elements = self.driver.find_elements(By.XPATH, specific_xpath)
                    
                    logger.info(f"找到{len(elements)}个包含'新鼎宋滩电站'文本的元素")
                    
                    for element in elements:
                        try:
                            if element.is_displayed():
                                logger.info(f"找到显示的匹配元素: '{element.text}'")
                                # 滚动到元素可见
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                time.sleep(2)
                                # 尝试点击
                                try:
                                    element.click()
                                except:
                                    self.driver.execute_script("arguments[0].click();", element)
                                
                                logger.info(f"成功选择项目: 新鼎宋滩电站")
                                time.sleep(5)
                                return True
                        except Exception as e:
                            logger.warning(f"处理元素时出错: {str(e)}")
                            continue
                except Exception as e:
                    logger.warning(f"宋滩项目特殊处理失败: {str(e)}")
            else:
                # 对其他项目使用策略1
                logger.info("策略1: 基于左侧项目树的查找")
                try:
                    # 先等待左侧项目树加载完成
                    WebDriverWait(self.driver, 25).until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'nco-station-left-tree-wrapper'))
                    )
                    
                    # 使用更精确的XPath查找节点行元素
                    project_elements = self.driver.find_elements(By.XPATH, 
                        '//li[contains(@class, "node-line")]//span[contains(@class, "node-name")] | ' +
                        '//li[contains(@class, "node-line")]//div[contains(@class, "flex-node-line-name-part")]'
                    )
                    
                    logger.info(f"找到{len(project_elements)}个可能的项目节点")
                    
                    # 打印所有找到的项目节点文本用于调试
                    for i, element in enumerate(project_elements):
                        try:
                            text = element.text.strip()
                            if text:
                                logger.debug(f"项目节点 {i+1}: '{text}'")
                        except Exception as e:
                            logger.warning(f"获取项目节点文本失败: {str(e)}")
                            continue
                    
                    # 查找匹配的项目节点
                    for element in project_elements:
                        try:
                            element_text = element.text
                            # 检查元素文本是否包含映射后的项目名称或原始项目名称
                            if mapped_project_name in element_text or project_name in element_text:
                                # 确保元素可点击
                                logger.info(f"找到匹配的项目节点: '{element_text}'")
                                # 滚动到元素可见
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                time.sleep(2)
                                # 等待元素可点击
                                WebDriverWait(self.driver, 15).until(
                                    EC.element_to_be_clickable(element)
                                )
                                # 尝试点击元素
                                try:
                                    element.click()
                                except Exception as click_e:
                                    logger.warning(f"直接点击失败，尝试使用JavaScript点击: {str(click_e)}")
                                    self.driver.execute_script("arguments[0].click();", element)
                                
                                logger.info(f"成功选择项目: {project_name} (匹配: {element_text})")
                                time.sleep(5)  # 增加等待时间让页面加载
                                return True
                        except Exception as e:
                            logger.warning(f"处理项目节点时出错: {str(e)}")
                            continue
                except Exception as nav_e:
                    logger.warning(f"策略1执行失败: {str(nav_e)}")
            
            # 策略2: 基于主内容区的查找（使用映射后的项目名称）
            logger.info("策略2: 基于主内容区的查找")
            try:
                content_projects = self.driver.find_elements(By.XPATH, 
                    '//div[contains(@class, "main-content-wrapper")]//div | '+ 
                    '//div[contains(@class, "main-content-wrapper")]//span'
                )
                
                logger.info(f"找到{len(content_projects)}个内容区域元素")
                
                for element in content_projects:
                    try:
                        element_text = element.text
                        if mapped_project_name in element_text or project_name in element_text:
                            logger.info(f"在内容区找到匹配项目: '{element_text}'")
                            # 滚动到元素可见
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                            time.sleep(2)
                            element.click()
                            logger.info(f"成功选择项目: {project_name} (匹配: {element_text})")
                            time.sleep(3)
                            return True
                    except Exception as e:
                        continue
            except Exception as e:
                logger.warning(f"策略2执行失败: {str(e)}")
            
            # 策略3: 使用更通用的XPath表达式查找
            logger.info("策略3: 使用通用XPath表达式查找")
            try:
                # 查找任何包含项目名称的元素
                generic_xpath = f"//*[contains(text(), '{mapped_project_name}') or contains(text(), '{project_name}')]"
                all_matching_elements = self.driver.find_elements(By.XPATH, generic_xpath)
                
                logger.info(f"找到{len(all_matching_elements)}个包含项目名称的元素")
                
                for element in all_matching_elements:
                    try:
                        if element.is_displayed():
                            logger.info(f"找到显示的匹配元素: '{element.text}'")
                            # 滚动到元素可见
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                            time.sleep(2)
                            # 尝试点击
                            try:
                                element.click()
                            except:
                                self.driver.execute_script("arguments[0].click();", element)
                            logger.info(f"成功选择项目: {project_name} (匹配: {element.text})")
                            time.sleep(3)
                            return True
                    except Exception as e:
                        continue
            except Exception as e:
                logger.warning(f"策略3执行失败: {str(e)}")
                         
            except Exception as nav_e:
                logger.warning(f"导航项目时出错: {str(nav_e)}")
            
            logger.warning(f"未找到项目: {project_name}")
            return False
        except Exception as e:
            logger.error(f"导航到项目失败: {str(e)}")
            return False
    
    def extract_daily_generation(self):
        """提取本日发电量数据"""
        try:
            logger.info("开始提取本日发电量数据")
            
            # 检查项目ID
            current_project_id = None
            if hasattr(self, 'current_project_id'):
                current_project_id = self.current_project_id
                logger.info(f"当前项目ID: {current_project_id}")
                
            # 对于id3项目，需要先在nco-energy-trends-body根元素下的class=value元素上悬停以显示tooltip
            if current_project_id in ['3', 3]:
                logger.info("处理id3项目，在nco-energy-trends-body根元素下的class=value元素上模拟鼠标悬停以显示tooltip")
                try:
                    # 先查找nco-energy-trends-body根元素
                    trends_body = self.driver.find_element(By.CLASS_NAME, 'nco-energy-trends-body')
                    logger.info("找到nco-energy-trends-body根元素")
                    
                    # 只在nco-energy-trends-body根元素下查找class=value的元素
                    value_elements = trends_body.find_elements(By.CLASS_NAME, 'value')
                    logger.info(f"在nco-energy-trends-body下找到{len(value_elements)}个class=value的元素")
                    
                    # 创建ActionChains对象用于模拟鼠标操作
                    actions = ActionChains(self.driver)
                    
                    # 对每个value元素尝试悬停
                    for value_element in value_elements:
                        try:
                            # 确保元素可见
                            if value_element.is_displayed():
                                # 模拟鼠标悬停
                                actions.move_to_element(value_element).perform()
                                logger.info("成功在value元素上悬停")
                                
                                # 等待短暂时间让tooltip出现
                                time.sleep(0.5)
                                
                                # 查找dpdesign-tooltip-inner元素
                                tooltip_elements = self.driver.find_elements(By.CLASS_NAME, 'dpdesign-tooltip-inner')
                                logger.info(f"悬停后找到{len(tooltip_elements)}个dpdesign-tooltip-inner元素")
                                
                                # 从tooltip中提取数据
                                for tooltip_element in tooltip_elements:
                                    try:
                                        # 获取元素的文本内容
                                        text = tooltip_element.text.strip()
                                        if text:
                                            # 提取数值
                                            import re
                                            # 支持带千位分隔符的数字
                                            match = re.search(r'([\d,]+(?:\.\d+)?)', text)
                                            if match:
                                                # 去除千位分隔符后转换为浮点数
                                                value_str = match.group(1).replace(',', '')
                                                value = float(value_str)
                                                logger.info(f"成功从dpdesign-tooltip-inner提取本日发电量: {value} kWh")
                                                return value
                                    except Exception as tooltip_e:
                                        logger.warning(f"处理tooltip元素时出错: {str(tooltip_e)}")
                        except Exception as hover_e:
                            logger.warning(f"在value元素上悬停时出错: {str(hover_e)}")
                            # 继续尝试下一个元素
                except Exception as e:
                    logger.warning(f"id3项目从dpdesign-tooltip-inner提取失败: {str(e)}")
                    # 继续尝试普通策略
            
            # 对于id4项目，保持原有逻辑
            elif current_project_id in ['4', 4]:
                logger.info("处理id4项目，从nco-energy-trends-body元素中提取数据")
                try:
                    # 查找nco-energy-trends-body根元素
                    trends_body = self.driver.find_element(By.CLASS_NAME, 'nco-energy-trends-body')
                    logger.info("找到nco-energy-trends-body根元素")
                    
                    # 查找class=value的元素
                    target_elements = trends_body.find_elements(By.CLASS_NAME, 'value')
                    logger.info(f"找到{len(target_elements)}个class='value'的元素")
                    
                    for element in target_elements:
                        try:
                            # 获取元素的文本内容
                            text = element.text.strip()
                            if text:
                                # 提取数值
                                import re
                                # 支持带千位分隔符的数字
                                match = re.search(r'([\d,]+(?:\.\d+)?)', text)
                                if match:
                                    # 去除千位分隔符后转换为浮点数
                                    value_str = match.group(1).replace(',', '')
                                    value = float(value_str)
                                    logger.info(f"成功从nco-energy-trends-body提取本日发电量: {value} kWh")
                                    return value
                        except Exception as e:
                            logger.warning(f"处理元素时出错: {str(e)}")
                except Exception as e:
                    logger.warning(f"id4项目提取失败: {str(e)}")
                    # 继续尝试普通策略
            
            # 主要策略: 查找nco-single-energy-body根元素下class=value且包含title属性的元素
            try:
                energy_body = self.driver.find_element(By.CLASS_NAME, 'nco-single-energy-body')
                logger.info("找到nco-single-energy-body根元素")
                
                # 查找class=value且包含title属性的元素
                target_elements = energy_body.find_elements(By.XPATH, ".//*[contains(@class, 'value') and @title]")
                logger.info(f"找到{len(target_elements)}个class='value'且包含title属性的元素")
                
                for element in target_elements:
                    try:
                        title = element.get_attribute('title')
                        if title:
                            # 提取数值
                            import re
                            # 改进的正则表达式，支持带千位分隔符的数字
                            match = re.search(r'([\d,]+(?:\.\d+)?)', title)
                            if match:
                                # 去除千位分隔符后转换为浮点数
                                value_str = match.group(1).replace(',', '')
                                value = float(value_str)
                                logger.info(f"成功提取本日发电量: {value} kWh")
                                return value
                    except Exception as e:
                        logger.warning(f"处理元素时出错: {str(e)}")
            except Exception as e:
                logger.warning(f"主要策略提取失败: {str(e)}")
                
            # 备用策略: 简化的XPath查找
            try:
                backup_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'nco-single-energy-body')]//*[contains(@class, 'value') and @title]")
                logger.info(f"找到{len(backup_elements)}个备用匹配元素")
                
                for element in backup_elements:
                    try:
                        title = element.get_attribute('title')
                        if title:
                            import re
                            # 改进的正则表达式，支持带千位分隔符的数字
                            match = re.search(r'([\d,]+(?:\.\d+)?)', title)
                            if match:
                                # 去除千位分隔符后转换为浮点数
                                value_str = match.group(1).replace(',', '')
                                value = float(value_str)
                                logger.info(f"成功从备用策略提取本日发电量: {value} kWh")
                                return value
                    except Exception as e:
                        logger.warning(f"处理备用元素时出错: {str(e)}")
            except Exception as e:
                logger.warning(f"备用策略提取失败: {str(e)}")
                
            logger.warning("未能提取本日发电量数据")
            return None
        except Exception as e:
            logger.error(f"提取本日发电量时发生异常: {str(e)}")
            return None
            
    def capture_power_curve(self, project_id):
        """截图发电曲线图"""
        try:
            # 保存当前项目ID为实例变量，供extract_daily_generation方法使用
            self.current_project_id = project_id
            
            logger.info(f"开始处理项目 {project_id}")
            time.sleep(5)  # 基础等待时间

            # 检查项目ID，对于 id3 和 id4 不执行页面滑动操作
            skip_scroll = project_id in ['3', '4', 3, 4]

            if not skip_scroll:
                logger.info("开始执行页面滚动逻辑")

                # 记录页面初始位置（window 层面）
                try:
                    initial_window_scroll = self.driver.execute_script(
                        "return window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;"
                    )
                except Exception:
                    initial_window_scroll = 0

                custom_scroll_container = None
                scrolled = False

                # 通过 JS 自动找出"最可能可滚动"的元素（权重：scrollHeight - clientHeight 最大）
                find_scrollable_js = """
                return (function(){
                  const els = Array.from(document.querySelectorAll('body, html, *'));
                  let best = null;
                  let bestScore = 0;
                  for (const el of els) {
                    try {
                      const style = window.getComputedStyle(el);
                      const overflowY = style.overflowY;
                      const scrollable = el.scrollHeight - el.clientHeight;
                      const isCandidate = (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay');
                      if (scrollable > bestScore && (isCandidate || scrollable > 0)) {
                        bestScore = scrollable;
                        best = el;
                      }
                    } catch(e) { /* ignore */ }
                  }
                  if (!best) {
                    return document.scrollingElement || document.documentElement || document.body;
                  }
                  return best;
                })();
                """

                try:
                    custom_scroll_container = self.driver.execute_script(find_scrollable_js)
                    info = self.driver.execute_script(
                        "var el = arguments[0]; return {tag: el.tagName, id: el.id || '', classes: el.className || '', scrollHeight: el.scrollHeight, clientHeight: el.clientHeight};",
                        custom_scroll_container
                    )
                    logger.info(f"自动检测到滚动容器: {info}")
                except Exception as e:
                    logger.warning(f"检测滚动容器失败: {e}")
                    custom_scroll_container = None

                # 如果检测到容器，尝试对该容器进行渐进式滚动（分段累进）
                if custom_scroll_container:
                    try:
                        container_initial = self.driver.execute_script("return arguments[0].scrollTop || 0;", custom_scroll_container)
                        logger.info(f"容器初始 scrollTop: {container_initial}")
                        # 分段滚动、多次判断（避免一次跳到底无反应）
                        for i in range(15):
                            self.driver.execute_script("arguments[0].scrollTop += arguments[1];", custom_scroll_container, 800)
                            time.sleep(0.35)
                            cur = self.driver.execute_script("return arguments[0].scrollTop;", custom_scroll_container)
                            logger.info(f"第{i+1}次容器滚动后 scrollTop={cur}")
                            if cur and cur > container_initial:
                                scrolled = True
                                break
                    except Exception as e:
                        logger.warning(f"容器滚动出错: {e}")

                # 页面级兜底：尝试 window.scrollTo
                if not scrolled:
                    try:
                        logger.info("尝试 window.scrollTo 滚动到底部")
                        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1.2)
                        final_window_scroll = self.driver.execute_script(
                            "return window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;"
                        )
                        logger.info(f"window.scrollTo 后 pageYOffset={final_window_scroll}")
                        if final_window_scroll and final_window_scroll > initial_window_scroll:
                            scrolled = True
                    except Exception as e:
                        logger.warning(f"window.scrollTo 出错: {e}")

                # 如果 JS 强制设置不生效，尝试模拟真实用户交互（点击 + PAGE_DOWN）
                if not scrolled:
                    try:
                        logger.info("尝试模拟用户交互（点击 body + PAGE_DOWN）")
                        body = self.driver.find_element(By.TAG_NAME, "body")
                        # 点击以获得焦点
                        ActionChains(self.driver).move_to_element(body).click().perform()
                        time.sleep(0.25)
                        # 连续发送 PAGE_DOWN
                        for _ in range(8):
                            ActionChains(self.driver).send_keys(Keys.PAGE_DOWN).perform()
                            time.sleep(0.4)
                        final_window_scroll = self.driver.execute_script(
                            "return window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;"
                        )
                        logger.info(f"模拟键盘后 pageYOffset={final_window_scroll}")
                        if final_window_scroll and final_window_scroll > initial_window_scroll:
                            scrolled = True
                    except Exception as e:
                        logger.warning(f"模拟键盘失败: {e}")
                
                # 最后一招：使用 execute_async_script 做逐步动画滚动（可触发某些懒加载）
                if not scrolled:
                    try:
                        logger.info("尝试 JS 动画逐步滚动（execute_async_script）")
                        js_animate = '''
                        var callback = arguments[arguments.length-1];
                        var el = arguments[0];
                        var step = arguments[1] || 500;
                        var delay = arguments[2] || 120;
                        var maxTime = arguments[3] || 15000;
                        var start = Date.now();
                        function stepScroll(){
                          try {
                            if (!el || el === window || el === document || el === document.scrollingElement) {
                              window.scrollBy(0, step);
                            } else {
                              el.scrollTop += step;
                            }
                          } catch(e) {}
                          if (Date.now() - start > maxTime) return callback(true);
                          if ((el === window || el === document || el === document.scrollingElement) && 
                              (window.pageYOffset + window.innerHeight >= document.body.scrollHeight)) {
                            return callback(true);
                          }
                          if (el !== window && el !== document && el !== document.scrollingElement) {
                            if (el.scrollTop + el.clientHeight >= el.scrollHeight) return callback(true);
                          }
                          setTimeout(stepScroll, delay);
                        }
                        stepScroll();
                        '''
                        # execute_async_script 会等待 callback 调用完毕
                        self.driver.execute_async_script(js_animate, custom_scroll_container, 800, 120, 12000)
                        time.sleep(0.8)
                        final_window_scroll = self.driver.execute_script(
                            "return window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;"
                        )
                        logger.info(f"JS 动画滚动后 pageYOffset={final_window_scroll}")
                        if final_window_scroll and final_window_scroll > initial_window_scroll:
                            scrolled = True
                    except Exception as e:
                        logger.warning(f"JS 动画滚动失败: {e}")
                
                if scrolled:
                    logger.info("滚动已触发（或页面高度变化），已完成滚动步骤")
                else:
                    logger.warning("尝试了多种滚动策略仍未能滚动：可能原因 -> 页面使用 iframe / shadow DOM / transform(translateY) 或者使用虚拟化(virtualized list)。建议在浏览器 devtools 检查真正滚动的元素或是否被 iframe 包裹。")

            # 新增：点击'前一日'按钮，让页面切换到前一天的数据
            logger.info("尝试点击'前一日'按钮")
            try:
                # 使用CSS选择器定位按钮：span[title='前一日']
                previous_day_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "span[title='前一日']"))
                )
                logger.info("找到'前一日'按钮")
                
                # 点击按钮
                previous_day_button.click()
                logger.info("点击'前一日'按钮成功")
                
                # 等待2秒，确保页面数据刷新完成
                time.sleep(2)
                logger.info("已等待2秒，页面数据应已刷新完成")
            except Exception as e:
                logger.warning(f"点击'前一日'按钮失败或未找到按钮: {str(e)}")
                # 如果找不到按钮，继续执行后续操作，不中断流程

            # 对于id3和id4的特殊处理，因为它们少了nco-single-energy-header元素
            is_project3_or_4 = project_id in ['3', '4', 3, 4]
            
            # 优先处理id3和id4项目
            if is_project3_or_4:
                logger.info("优先处理id3和id4项目，直接查找nco-energy-trends-body根元素")
                try:
                    # 直接找到根元素nco-energy-trends-body
                    root_element = self.driver.find_element(By.CLASS_NAME, 'nco-energy-trends-body')
                    logger.info("找到id3和id4的根元素nco-energy-trends-body")
                        
                    # 使用根元素作为截图区域
                    screenshot_element = root_element
                    logger.info("直接使用nco-energy-trends-body根元素作为截图区域")
                        
                    # 设置截图路径
                    screenshot_path = os.path.join(self.screenshots_dir, f"power_curve_{project_id}.png")
                    # 在截图前将鼠标移动到页面左上角，确保鼠标不在截图区域悬停
                    ActionChains(self.driver).move_to_element_with_offset(self.driver.find_element(By.TAG_NAME, 'body'), 0, 0).perform()
                    # 短暂等待确保鼠标移动完成
                    time.sleep(0.5)
                    # 直接对根元素进行截图
                    screenshot_element.screenshot(screenshot_path)
                    logger.info(f"id3/id4项目截图成功，已保存至: {screenshot_path}")
                        
                    # 读取并调整尺寸为585*290
                    # 读取并调整尺寸
                    try:
                        with Image.open(screenshot_path) as img:
                            if is_project3_or_4:
                                target_size = (585, 290)
                            else:
                                target_size = (565, 320)
                            resized_img = img.resize(target_size, Image.Resampling.LANCZOS)
                            resized_img.save(screenshot_path)
                            logger.info(f"id3/id4项目截图已调整尺寸为585*290")
                    except Exception as resize_e:
                        logger.warning(f"id3/id4项目截图调整尺寸失败: {str(resize_e)}")
                        
                    # 获取日发电量数据
                    daily_generation = self.extract_daily_generation()
                    return screenshot_path, daily_generation
                except Exception as e:
                    logger.warning(f"id3/id4项目找不到nco-energy-trends-body根元素: {str(e)}")
                    # 如果找不到根元素，继续执行后续的查找策略
            
            # 基于用户提供的界面截图，我们知道需要截图的是能量管理标签下的发电曲线图
            target_element = None
            
            # 策略1: 基于用户提供的界面截图，查找能量管理区域的图表
            logger.info("使用新策略查找能量管理区域的图表")
            
            # 先尝试查找包含能量管理文本的元素，确定图表所在的区域
            try:
                energy_management_section = self.driver.find_element(By.XPATH, "//h3[contains(text(), '能量管理')]/ancestor::div[contains(@class, 'business-station-overview-content')]")
                logger.info("找到能量管理区域")
                
                # 在能量管理区域内查找图表容器
                try:
                    # 查找包含标题'发电量'的图表容器
                    chart_container = energy_management_section.find_element(By.XPATH, ".//div[contains(@class, 'chart-container') or contains(@class, 'chart-wrapper')]")
                    logger.info("在能量管理区域找到图表容器")
                    target_element = chart_container
                except:
                    logger.warning("在能量管理区域未找到直接的图表容器")
                    
                    # 尝试查找canvas元素作为备选
                    try:
                        canvas_elements = energy_management_section.find_elements(By.TAG_NAME, 'canvas')
                        if canvas_elements:
                            logger.info(f"在能量管理区域找到{len(canvas_elements)}个canvas元素")
                            # 选择第一个canvas元素的父容器
                            target_element = canvas_elements[0].find_element(By.XPATH, '..')
                    except:
                        logger.warning("在能量管理区域查找canvas元素失败")
            except:
                logger.warning("查找能量管理区域失败")
                
            # 策略2: 如果上述方法失败，尝试使用原来的定位策略
            if not target_element:
                logger.info("尝试使用原始定位策略")
                try:
                    energy_body_element = self.driver.find_element(By.CLASS_NAME, 'nco-single-energy-body')
                    logger.info("找到nco-single-energy-body根元素")
                    target_element = energy_body_element
                except:
                    logger.warning("查找nco-single-energy-body根元素失败")
                    
                    try:
                        echarts_element = self.driver.find_element(By.CLASS_NAME, 'echarts-for-react')
                        logger.info("直接找到echarts-for-react元素")
                        target_element = echarts_element
                    except:
                        logger.warning("直接查找echarts-for-react元素失败")
            
            # 如果找到目标元素，则进行截图
            if target_element:
                # 直接使用找到的目标元素作为截图对象，避免因额外div导致的问题
                screenshot_element = target_element
                logger.info("直接使用找到的目标元素进行截图，避免因额外div导致的问题")
                
                # 设置截图路径
                screenshot_path = os.path.join(self.screenshots_dir, f"power_curve_{project_id}.png")
                
                # 截图并调整尺寸为565*320
                try:
                    # 先获取当前元素的实际尺寸信息用于调试
                    element_location = screenshot_element.location
                    element_size = screenshot_element.size
                    logger.info(f"找到的元素位置: {element_location}, 大小: {element_size}")
                    
                    # 为了确保获取到正确的区域，尝试使用完整页面截图然后裁剪
                    # 先截取整个页面
                    full_screenshot_binary = self.driver.get_screenshot_as_png()
                    
                    # 将二进制数据转换为PIL图像对象
                    full_screenshot = Image.open(io.BytesIO(full_screenshot_binary))
                    
                    # 计算元素在页面中的绝对位置和大小
                    # 注意：WebDriver返回的坐标可能相对于视口，需要考虑滚动偏移
                    element_x = element_location['x']
                    element_y = element_location['y']
                    element_width = element_size['width']
                    element_height = element_size['height']
                    
                    # 在截图前将鼠标移动到页面左上角，确保鼠标不在截图区域悬停
                    ActionChains(self.driver).move_to_element_with_offset(self.driver.find_element(By.TAG_NAME, 'body'), 0, 0).perform()
                    # 短暂等待确保鼠标移动完成
                    time.sleep(0.5)
                    # 直接对元素进行截图
                    screenshot_element.screenshot(screenshot_path)
                    logger.info(f"使用元素直接截图成功，已保存至: {screenshot_path}")
                    
                    # 读取并调整尺寸
                    try:
                        with Image.open(screenshot_path) as img:
                            if is_project3_or_4:
                                target_size = (585, 290)
                            else:
                                target_size = (565, 320)
                            resized_img = img.resize(target_size, Image.Resampling.LANCZOS)
                            resized_img.save(screenshot_path)
                            logger.info(f"截图已调整尺寸为{target_size[0]}x{target_size[1]}")
                    except Exception as resize_e:
                        logger.warning(f"截图调整尺寸失败: {str(resize_e)}")
                    
                    # 提取本日发电量数据
                    daily_generation = self.extract_daily_generation()
                    
                    logger.info(f"项目 {project_id} 处理完成")
                    return screenshot_path, daily_generation
                except Exception as backup_e:
                    logger.error(f"备用截图方法也失败: {str(backup_e)}")
                    return False, None
            else:
                logger.error("未找到发电曲线图元素，无法截图")
                return False, None
        except Exception as e:
            logger.error(f"截图发电曲线时发生异常: {str(e)}")
            return False, None
    
    def run(self):
        """运行完整的爬取流程"""
        try:
            # 登录
            if not self.login():
                logger.error("登录失败，无法继续爬取")
                return False
            
            # 为每个项目截图并提取数据
            results = {}
            for project in self.projects:
                project_name = project['name']
                project_id = project['id']
                
                # 导航到项目
                if self.navigate_to_project(project_name):
                    # 截图发电曲线并提取本日发电量
                    screenshot_path, daily_generation = self.capture_power_curve(project_id)
                    
                    # 存储结果
                    results[project_id] = {
                        'screenshot_path': screenshot_path,
                        'daily_generation': daily_generation
                    }
                else:
                    logger.warning(f"跳过项目 {project_name}，因为无法导航到该项目")
                    results[project_id] = {
                        'screenshot_path': None,
                        'daily_generation': None
                    }
            
            logger.info("爬取完成！")
            return results
        except Exception as e:
            logger.error(f"爬取过程中出现错误: {str(e)}")
            raise

if __name__ == "__main__":
    # 示例用法
    # 注意：在实际使用时，建议从环境变量或安全的配置文件中读取用户名和密码
    USERNAME = "xinding"  # 替换为实际用户名
    PASSWORD = "0000000a"  # 替换为实际密码
    
    # 要爬取的项目列表
    PROJECTS = [
        {'name': '宋滩', 'id': '1'},
        {'name': '李赞皇', 'id': '2'},
        {'name': '滨北南邱', 'id': '3'},
        {'name': '水立方', 'id': '4'},
        # 可以添加更多项目
    ]
    
    # 创建并运行爬虫
    with HuaweiFusionSolarScraper(USERNAME, PASSWORD, PROJECTS) as scraper:
        results = scraper.run()
        
        # 打印结果
        if results:
            logger.info("爬取结果:")
            for project_id, result in results.items():
                logger.info(f"项目ID {project_id}:")
                logger.info(f"  截图已保存到: {result['screenshot_path']}")
                logger.info(f"  本日发电量: {result['daily_generation']} kWh")
