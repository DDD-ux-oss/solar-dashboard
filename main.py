#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gitee CI入口点
"""

import sys
import os
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加调试输出
print("=== main.py 开始执行 ===")
print(f"当前工作目录: {os.getcwd()}")
print(f"文件存在性: {os.path.exists(__file__)} 路径: {__file__}")
print(f"Python 版本: {sys.version}")

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    logger.info("导入update_solar_dashboard模块")
    import update_solar_dashboard
    
    logger.info("执行update_solar_dashboard模块的主函数")
    
    # 如果模块有main函数，调用它
    if hasattr(update_solar_dashboard, 'main'):
        logger.info("调用update_solar_dashboard.main()")
        update_solar_dashboard.main()
    else:
        # 否则，检查是否有if __name__ == "__main__"块
        logger.info("update_solar_dashboard模块没有main函数，直接执行模块")
        exec(open('update_solar_dashboard.py', encoding='utf-8').read())
        
    logger.info("主程序执行成功")
    sys.exit(0)
except Exception as e:
    logger.error(f"主程序执行出错: {str(e)}")
    print(f"主程序执行出错: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)