# GitHub Actions 无法访问华为域名解决方案

## 问题分析

您在GitHub Actions中运行太阳能数据爬虫脚本时遇到了`net::ERR_NAME_NOT_RESOLVED`错误，这表明GitHub Actions环境无法解析华为相关域名（如`intl.fusionsolar.huawei.com`）。

### 可能的原因

1. **DNS解析问题**：GitHub Actions环境的DNS服务器无法解析华为域名
2. **IP访问限制**：华为服务器可能对GitHub Actions的IP地址范围进行了访问限制
3. **网络连接问题**：GitHub Actions与华为服务器之间的网络连接存在问题
4. **防火墙或安全策略**：华为或GitHub的安全策略阻止了连接

## 解决方案

### 1. 修改DNS配置

在GitHub Actions工作流中使用公共DNS服务器（如Google DNS或Cloudflare DNS）：

```yaml
# 在workflow文件中添加以下步骤
sudo rm -f /etc/resolv.conf
sudo bash -c 'echo "nameserver 8.8.8.8" > /etc/resolv.conf'
sudo bash -c 'echo "nameserver 8.8.4.4" >> /etc/resolv.conf'
```

### 2. 使用代理服务器

如果您有可用的代理服务器，可以在GitHub Actions中配置使用：

```yaml
# 设置环境变量
- name: 设置代理环境变量
  run: |
    echo "HTTP_PROXY=${{ secrets.HTTP_PROXY }}" >> $GITHUB_ENV
    echo "HTTPS_PROXY=${{ secrets.HTTPS_PROXY }}" >> $GITHUB_ENV
    echo "NO_PROXY=${{ secrets.NO_PROXY }}" >> $GITHUB_ENV
```

### 3. 实现重试机制

在脚本中添加重试机制，提高连接成功率：

```python
import time
import requests

def retry_request(url, max_retries=3, delay=5):
    for i in range(max_retries):
        try:
            response = requests.get(url, timeout=30)
            return response
        except Exception as e:
            print(f"请求失败 (尝试 {i+1}/{max_retries}): {e}")
            if i < max_retries - 1:
                print(f"{delay}秒后重试...")
                time.sleep(delay)
    return None
```

### 4. 使用直接IP访问

如果您能获取到华为服务器的IP地址，可以尝试直接使用IP访问：

```python
import requests

# 直接使用IP地址并设置Host头
def request_with_ip(url, ip_address):
    headers = {
        'Host': url.split('//')[1].split('/')[0]  # 提取域名部分
    }
    
    # 构造IP访问URL
    ip_url = url.replace(url.split('//')[1].split('/')[0], ip_address)
    
    try:
        response = requests.get(ip_url, headers=headers, verify=False)
        return response
    except Exception as e:
        print(f"直接IP访问失败: {e}")
        return None
```

### 5. 使用备用域名解析方法

在脚本中使用`socket`模块手动解析域名：

```python
import socket
import requests

def get_ip_address(domain):
    try:
        ip_address = socket.gethostbyname(domain)
        return ip_address
    except socket.gaierror:
        print(f"无法解析域名: {domain}")
        return None
```

## 修改GitHub Actions工作流

基于以上解决方案，以下是修改后的GitHub Actions工作流文件：

```yaml
name: 太阳能数据爬虫与更新

on:
  # 定期执行 - 每天北京时间上午9:30执行（UTC时间凌晨1:30）
  schedule:
    - cron: '30 1 * * *'
  # 允许手动触发
  workflow_dispatch:

permissions:
  contents: write
jobs:
  scrape-and-update:
    runs-on: ubuntu-latest

    steps:
      # 步骤1: 检出代码仓库
      - name: 检出代码
        uses: actions/checkout@v3
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      # 步骤2: 设置Python环境
      - name: 设置Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
          cache: 'pip'

      # 步骤3: 修改DNS配置（解决域名解析问题）
      - name: 修改DNS配置
        run: |
          sudo rm -f /etc/resolv.conf
          sudo bash -c 'echo "nameserver 8.8.8.8" > /etc/resolv.conf'
          sudo bash -c 'echo "nameserver 8.8.4.4" >> /etc/resolv.conf'
          cat /etc/resolv.conf

      # 步骤4: 安装系统依赖（Chrome浏览器和驱动）
      - name: 安装系统依赖
        run: |
          sudo apt-get update
          sudo apt-get install -y wget curl unzip libxss1 libxtst6 libxrandr2 libasound2t64 libpangocairo-1.0-0 libatk1.0-0 libcairo-gobject2 libgtk-3-0 libgdk-pixbuf2.0-0
          wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
          echo "deb [arch=amd64] https://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
          sudo apt-get update
          sudo apt-get install -y google-chrome-stable
          sudo apt-get install -y chromium-chromedriver

      # 步骤5: 测试DNS解析
      - name: 测试DNS解析
        run: |
          # 测试华为域名解析
          nslookup intl.fusionsolar.huawei.com
          nslookup huawei.com
          
          # 测试公共域名作为对照
          nslookup github.com
          nslookup google.com

      # 步骤6: 测试网络连接
      - name: 测试网络连接
        run: |
          ping -c 3 8.8.8.8
          curl -v https://intl.fusionsolar.huawei.com 2>&1 | head -50

      # 步骤7: 安装Python依赖
      - name: 安装Python依赖
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install webdriver-manager

      # 步骤8: 运行太阳能数据爬虫
      - name: 运行太阳能数据爬虫
        env:
          HUAWEI_USERNAME: ${{ secrets.HUAWEI_USERNAME }}
          HUAWEI_PASSWORD: ${{ secrets.HUAWEI_PASSWORD }}
          SEMS_USERNAME: ${{ secrets.SEMS_USERNAME }}
          SEMS_PASSWORD: ${{ secrets.SEMS_PASSWORD }}
          ESOLAR_USERNAME: ${{ secrets.ESOLAR_USERNAME }}
          ESOLAR_PASSWORD: ${{ secrets.ESOLAR_PASSWORD }}
        run: |
          export DISPLAY=:99
          Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 &

          echo "=== 运行爬虫脚本 ==="
          python3 update_solar_dashboard.py || {
            echo "ERROR: 脚本运行失败"
            exit 1
          }

      # 步骤9: 检查数据是否更新
      - name: 检查数据更新
        run: |
          if [ -s solar_data.json ]; then
            echo "数据文件存在且不为空"
            cat solar_data.json
          else
            echo "数据文件不存在或为空，退出工作流"
            exit 1
          fi

      # 步骤10: 提交更新的数据文件到仓库
      - name: 提交数据更新
        run: |
          git config --global user.name 'github-actions[bot]'
          git config --global user.email 'github-actions[bot]@users.noreply.github.com'

          git add solar_data.json screenshots/ data/
          git status

          if ! git diff --staged --quiet; then
            git commit -m "自动化更新太阳能数据 $(date +'%Y-%m-%d %H:%M:%S')"
            git push https://x-access-token:${{ secrets.GITHUB_TOKEN }}@github.com/${{ github.repository }} HEAD:main
            echo "数据已成功更新并推送到仓库"
          else
            echo "没有检测到数据更改，跳过提交"
          fi
```

## 脚本修改建议

以下是修改`update_solar_dashboard.py`脚本的建议，添加重试机制和备用DNS解析：

```python
# 在脚本开头添加以下函数
import socket
import time
import requests
from selenium.common.exceptions import WebDriverException

def resolve_domain_with_retry(domain, max_retries=5, delay=2):
    """使用重试机制解析域名"""
    for i in range(max_retries):
        try:
            ip_address = socket.gethostbyname(domain)
            return ip_address
        except socket.gaierror:
            print(f"DNS解析失败 (尝试 {i+1}/{max_retries}): {domain}")
            if i < max_retries - 1:
                print(f"{delay}秒后重试...")
                time.sleep(delay)
    return None

def create_chrome_options_with_dns():
    """创建Chrome选项并添加DNS设置"""
    from selenium.webdriver.chrome.options import Options
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    
    # 添加DNS服务器设置
    options.add_argument('--dns-servers=8.8.8.8,8.8.4.4')
    
    return options

def access_url_with_retry(driver, url, max_retries=3, delay=5):
    """使用重试机制访问URL"""
    for i in range(max_retries):
        try:
            driver.get(url)
            return True
        except WebDriverException as e:
            if "ERR_NAME_NOT_RESOLVED" in str(e):
                print(f"域名解析失败 (尝试 {i+1}/{max_retries}): {url}")
                if i < max_retries - 1:
                    print(f"{delay}秒后重试...")
                    time.sleep(delay)
            else:
                print(f"访问URL失败: {e}")
                raise
    return False
```

## 其他注意事项

1. **手动运行测试**：在GitHub Actions中添加了DNS解析和网络连接测试步骤，您可以通过手动触发工作流来查看测试结果

2. **代理服务器**：如果修改DNS配置不起作用，可以考虑使用代理服务器。您需要在GitHub Secrets中添加代理配置（如`HTTP_PROXY`和`HTTPS_PROXY`），然后在工作流中使用

3. **IP地址访问**：如果您能获取到华为服务器的稳定IP地址，可以考虑使用直接IP访问的方式

4. **联系GitHub支持**：如果问题持续存在，您可以联系GitHub支持团队，询问是否有特定的网络限制

5. **使用Gitee CI替代**：由于您已经配置了Gitee CI，并且在Gitee上可以正常访问华为域名，可以考虑将爬虫任务转移到Gitee CI执行

## 后续步骤

1. 保存上述修改后的GitHub Actions工作流文件
2. 根据需要修改`update_solar_dashboard.py`脚本，添加重试机制
3. 手动触发工作流，查看测试结果
4. 根据测试结果选择最合适的解决方案

如果您需要进一步的帮助或有任何疑问，请随时提问。