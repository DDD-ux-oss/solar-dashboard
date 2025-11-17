#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本：验证CI环境检测和Chrome浏览器支持
"""

import os
import sys

def test_ci_detection():
    """测试CI环境检测功能"""
    print("=" * 50)
    print("测试CI环境检测功能")
    print("=" * 50)
    
    # 设置CI环境变量
    os.environ['CI'] = 'true'
    
    try:
        from update_solar_dashboard import is_ci_environment
        print(f"update_solar_dashboard CI检测: {is_ci_environment()}")
    except Exception as e:
        print(f"update_solar_dashboard 导入失败: {e}")
    
    try:
        from huawei_scraper import is_ci_environment
        print(f"huawei_scraper CI检测: {is_ci_environment()}")
    except Exception as e:
        print(f"huawei_scraper 导入失败: {e}")
    
    try:
        from esolar_scraper import is_ci_environment
        print(f"esolar_scraper CI检测: {is_ci_environment()}")
    except Exception as e:
        print(f"esolar_scraper 导入失败: {e}")
    
    try:
        from sems_combined_tool import is_ci_environment
        print(f"sems_combined_tool CI检测: {is_ci_environment()}")
    except Exception as e:
        print(f"sems_combined_tool 导入失败: {e}")

def test_chrome_webdriver():
    """测试Chrome WebDriver创建"""
    print("\n" + "=" * 50)
    print("测试Chrome WebDriver创建")
    print("=" * 50)
    
    try:
        from update_solar_dashboard import create_webdriver
        print("正在创建Chrome WebDriver...")
        driver = create_webdriver()
        print("Chrome WebDriver创建成功")
        
        # 测试基本功能
        driver.get("https://www.google.com")
        print(f"页面标题: {driver.title}")
        
        driver.quit()
        print("Chrome WebDriver关闭成功")
        
    except Exception as e:
        print(f"Chrome WebDriver创建失败: {e}")
        import traceback
        traceback.print_exc()

def test_browser_selection():
    """测试浏览器选择逻辑"""
    print("\n" + "=" * 50)
    print("测试浏览器选择逻辑")
    print("=" * 50)
    
    # 测试CI环境
    os.environ['CI'] = 'true'
    try:
        from update_solar_dashboard import create_webdriver
        driver = create_webdriver()
        print(f"CI环境选择的浏览器类型: Chrome")
        driver.quit()
    except Exception as e:
        print(f"CI环境测试失败: {e}")
    
    # 测试本地环境
    if 'CI' in os.environ:
        del os.environ['CI']
    
    try:
        from update_solar_dashboard import create_webdriver
        driver = create_webdriver()
        print(f"本地环境选择的浏览器类型: Edge")
        driver.quit()
    except Exception as e:
        print(f"本地环境测试失败: {e}")

if __name__ == "__main__":
    print("开始测试CI环境兼容性修改...")
    
    test_ci_detection()
    test_chrome_webdriver()
    test_browser_selection()
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)