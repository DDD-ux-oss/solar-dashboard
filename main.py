#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gitee CI入口点
这个文件的作用是作为Gitee CI的入口点，因为CI尝试执行python3 ./main.py
"""

import update_solar_dashboard
import sys
import os
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """执行太阳能仪表盘更新的主函数"""
    try:
        # 从环境变量中读取用户名和密码
        HUAWEI_USERNAME = os.environ.get('HUAWEI_USERNAME', "xinding")
        HUAWEI_PASSWORD = os.environ.get('HUAWEI_PASSWORD', "0000000a")
        SEMS_USERNAME = os.environ.get('SEMS_USERNAME', "15965432272")
        SEMS_PASSWORD = os.environ.get('SEMS_PASSWORD', "xdny123456")
        ESOLAR_USERNAME = os.environ.get('ESOLAR_USERNAME', "18663070009")
        ESOLAR_PASSWORD = os.environ.get('ESOLAR_PASSWORD', "Aa18663070009")
        
        # 打印环境变量状态（不打印具体值）
        logger.info(f"环境变量配置状态: HUAWEI_USERNAME={'已设置' if HUAWEI_USERNAME else '未设置'}")
        logger.info(f"环境变量配置状态: SEMS_USERNAME={'已设置' if SEMS_USERNAME else '未设置'}")
        logger.info(f"环境变量配置状态: ESOLAR_USERNAME={'已设置' if ESOLAR_USERNAME else '未设置'}")
        
        # 初始化太阳能仪表盘更新器
        updater = update_solar_dashboard.SolarDashboardUpdater(
            HUAWEI_USERNAME, 
            HUAWEI_PASSWORD,
            SEMS_USERNAME,
            SEMS_PASSWORD,
            ESOLAR_USERNAME,
            ESOLAR_PASSWORD
        )
        
        # 确保目录存在
        os.makedirs(updater.base_data_dir, exist_ok=True)
        os.makedirs(updater.base_screenshots_dir, exist_ok=True)
        os.makedirs(updater.reports_dir, exist_ok=True)
        
        logger.info(f"更新文件路径: {updater.data_file_path}")
        logger.info(f"截图目录路径: {updater.screenshots_dir}")
        
        # 更新仪表盘数据
        updater.update_dashboard()
        logger.info("太阳能仪表盘更新成功完成")
        return 0
    except Exception as e:
        logger.error(f"主程序执行出错: {str(e)}")
        print(f"主程序执行出错: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())