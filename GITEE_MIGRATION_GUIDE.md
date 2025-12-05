# Gitee + 流水线 迁移指南

本指南将帮助您将太阳能数据爬虫项目从GitHub迁移到Gitee，并使用Gitee流水线（Gitee CI）实现每天定时自动运行脚本。

## 1. 项目迁移到Gitee

### 步骤1：创建Gitee仓库
1. 登录Gitee（https://gitee.com）
2. 点击右上角「+」号，选择「新建仓库」
3. 填写仓库信息：
   - 仓库名称：建议与GitHub仓库名称一致
   - 仓库介绍：与原仓库保持一致
   - 选择公开或私有（根据需要）
   - 初始化README：不勾选（我们将导入现有项目）
4. 点击「创建」

### 步骤2：导入GitHub仓库（方法一：Gitee界面导入）
1. 进入刚创建的Gitee仓库
2. 点击「代码」标签页
3. 点击右上角「克隆/下载」按钮
4. 在弹出窗口中点击「导入仓库」
5. 选择「从URL导入」
6. 填写GitHub仓库地址（https://github.com/[用户名]/[仓库名].git）
7. 点击「导入」按钮

### 步骤2：导入GitHub仓库（方法二：Git命令行迁移）
如果界面导入失败或找不到相关选项，可以使用Git命令行迁移：

#### 在本地计算机上执行以下命令：
1. 克隆GitHub仓库到本地：
   ```bash
   git clone --mirror https://github.com/[用户名]/[仓库名].git
   cd [仓库名].git
   ```

2. 添加Gitee仓库作为远程仓库：
   ```bash
   git remote add gitee https://gitee.com/[用户名]/[仓库名].git
   ```

3. 推送所有代码到Gitee：
   ```bash
   git push gitee --all
   git push gitee --tags
   ```

4. 清理本地临时仓库：
   ```bash
   cd ..
   rm -rf [仓库名].git
   ```

### 步骤3：验证代码导入
1. 导入完成后，检查Gitee仓库中的代码是否完整
2. 确保所有文件都已成功导入，包括：
   - 主脚本文件：`update_solar_dashboard.py`
   - 爬虫模块：`huawei_scraper.py`、`esolar_scraper.py`、`sems_combined_tool.py`
   - 流水线配置：`.gitee-ci.yml`
   - 数据目录：`data/`、`screenshots/`

## 2. 配置Gitee流水线

### 步骤1：启用流水线
1. 进入仓库主页
2. 点击顶部导航栏中的「流水线」标签（如截图所示，在"统计"和"服务"之间）
3. 如果未自动启用流水线，点击「启用流水线」按钮

### 步骤2：配置环境变量和密钥

#### 方式一：使用访问令牌（推荐）
1. 进入仓库「管理」->「部署公钥与凭据」->「凭据管理」
2. 点击「添加令牌」，创建一个具有仓库读写权限的访问令牌：
   - 令牌名称：`GITEE_TOKEN`
   - 权限：至少勾选「仓库权限」->「读权限」和「写权限」
   - 有效期：根据需要设置

使用访问令牌的优势是配置简单，不需要修改流水线配置文件。

#### 方式二：使用部署公钥（如截图所示）
1. 进入仓库「管理」->「部署公钥与凭据」->「部署公钥」
2. 点击「添加部署公钥」按钮
3. 在弹出的「添加部署公钥」页面中：
   - **标题**：输入一个描述性名称（如 "流水线部署公钥"）
   - **公钥**：粘贴您生成的SSH公钥内容

   *生成SSH公钥的方法：*
   ```bash
   # 在本地计算机上执行以下命令生成SSH密钥对
   ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
   ```

   *查看公钥内容并复制：*
   - **Linux/Mac系统**：
     ```bash
     cat ~/.ssh/id_rsa.pub
     ```
   - **Windows系统**（PowerShell/Command Prompt）：
     ```cmd
     # 使用Windows路径格式（推荐）
     type C:\Users\YourUsername\.ssh\id_rsa.pub
     
     # 或者使用PowerShell变量（需要PowerShell）
     type ~/.ssh/id_rsa.pub
     ```
   
   **注意**：在Windows系统中，请确保将`YourUsername`替换为您的实际用户名，并且路径使用双反斜杠(\)或单斜杠(/)。

4. 点击「添加」按钮完成部署公钥的配置

5. **重要**：如果使用部署公钥，需要修改 `.gitee-ci.yml` 文件中的Git认证部分：
   ```yaml
   # 将这一行
   - git remote set-url origin https://oauth2:${GITEE_TOKEN}@gitee.com/${CI_REPOSITORY_URL#*//*/}
   # 改为
   - git remote set-url origin git@gitee.com:${CI_REPOSITORY_URL#*//*/}
   ```

使用部署公钥的优势是安全性更高，不需要在流水线中暴露访问令牌。

#### 添加环境变量
1. 进入仓库「管理」->「部署公钥与凭据」->「凭据管理」
2. 点击「添加密码」，添加以下环境变量：
   - `HUAWEI_USERNAME`：华为FusionSolar账号
   - `HUAWEI_PASSWORD`：华为FusionSolar密码
   - `SEMS_USERNAME`：SEMS系统账号
   - `SEMS_PASSWORD`：SEMS系统密码
   - `ESOLAR_USERNAME`：ESolar系统账号
   - `ESOLAR_PASSWORD`：ESolar系统密码

### 步骤3：配置流水线触发条件
1. 进入仓库「流水线」标签
2. 点击顶部的「通用变量」标签页
3. 如果需要调整定时执行时间，可以修改 `.gitee-ci.yml` 文件中的配置

## 3. 验证流水线

### 步骤1：手动触发流水线
1. 进入仓库「流水线」标签（如截图所示）
2. 点击您想要运行的流水线（如BranchPipeline或MasterPipeline）
3. 点击「运行流水线」按钮，手动触发一次执行

### 步骤2：查看执行日志
1. 在流水线列表中，点击刚触发的执行记录（如截图中BranchPipeline下的#1记录）
2. 查看每个步骤的执行日志，确保没有错误
3. 重点检查：
   - 依赖安装是否成功
   - 爬虫脚本是否正常运行
   - 数据是否成功更新并提交到仓库

### 步骤3：检查网站数据
1. 流水线执行成功后，检查 `solar_data.json` 文件是否已更新
2. 访问您的网站，确认爬取的数据已正确显示

## 4. 常见问题排查

### 问题1：流水线执行失败，提示缺少环境变量
**解决方法**：
- 检查Gitee仓库的「凭据管理」，确保所有必要的环境变量都已正确配置
- 检查变量名称是否与代码中的引用一致（区分大小写）

### 问题2：爬虫脚本运行失败，提示浏览器初始化错误
**解决方法**：
- 检查流水线日志中的浏览器安装步骤是否成功
- 确保CI环境中已正确安装Chrome浏览器和驱动

### 问题3：数据更新后未显示在网站上
**解决方法**：
- 检查流水线日志，确认数据已成功提交到仓库
- 检查网站是否正确读取了 `solar_data.json` 文件
- 清除网站缓存，刷新页面重试

## 5. 项目结构说明

### 核心文件
- `update_solar_dashboard.py`：主更新脚本，整合所有爬虫和数据处理逻辑
- `.gitee-ci.yml`：Gitee流水线配置
- `huawei_scraper.py`：华为FusionSolar数据爬虫
- `sems_combined_tool.py`：SEMS系统数据获取工具
- `esolar_scraper.py`：ESolar系统数据爬虫
- `solar_data.json`：最新爬取的数据文件

### 数据存储
- `data/`：按日期保存的历史数据文件
- `screenshots/`：爬虫过程中的截图

## 6. 自定义配置

### 修改执行时间
Gitee流水线的定时执行需通过界面设置：
1. 进入仓库「流水线」标签
2. 选择对应的流水线（如BranchPipeline）
3. 点击「设置」按钮
4. 在定时触发设置中配置执行时间

参考配置：每天UTC时间1:30（北京时间9:30）执行
```
30 1 * * *
```

### 添加新的项目或数据源
1. 在 `update_solar_dashboard.py` 中添加新项目配置
2. 编写对应的爬虫类（参考现有爬虫实现）
3. 集成到主更新流程中

## 7. 联系方式

如果您在迁移或使用过程中遇到问题，请随时联系项目维护者。