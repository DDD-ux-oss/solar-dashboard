#!/usr/bin/env python3
"""
检查CI环境中预装的Python包
"""
import sys
import subprocess

def check_package(package_name):
    """检查包是否已安装"""
    try:
        __import__(package_name)
        return True
    except ImportError:
        return False

def check_pip_package(package_name):
    """通过pip检查包是否已安装"""
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', 'show', package_name], 
                              capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

def main():
    print("=== CI环境Python包检查 ===")
    print(f"Python版本: {sys.version}")
    print(f"Python路径: {sys.executable}")
    print()
    
    # 常见的包列表
    packages_to_check = [
        'requests',
        'selenium', 
        'beautifulsoup4',
        'lxml',
        'pandas',
        'numpy',
        'easyocr',
        'webdriver-manager',
        'flask',
        'urllib3',
        'certifi'
    ]
    
    print("=== 直接导入检查 ===")
    for package in packages_to_check:
        if check_package(package):
            print(f"✅ {package} - 已安装")
        else:
            print(f"❌ {package} - 未安装")
    
    print("\n=== pip检查 ===")
    for package in packages_to_check:
        if check_pip_package(package):
            print(f"✅ {package} - 已通过pip安装")
        else:
            print(f"❌ {package} - 未通过pip安装")
    
    print("\n=== pip list ===")
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', 'list'], 
                              capture_output=True, text=True)
        print(result.stdout)
    except Exception as e:
        print(f"无法获取pip list: {e}")

if __name__ == "__main__":
    main()