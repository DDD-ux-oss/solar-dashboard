# 太阳能数据自动更新系统

本项目通过GitHub Actions实现太阳能数据和图表的自动化爬取与更新，无需本地电脑保持开机状态。

## 功能特点

- 自动爬取华为FusionSolar、SEMS和ESolar系统的数据和图表
- 对截图进行智能裁剪，确保展示效果一致
- 通过GitHub Actions每日定时运行，自动提交更新
- 支持手动触发工作流

## 自动更新设置方法

### 1. 准备工作

1. **创建GitHub仓库**：将本项目代码上传到GitHub仓库

2. **设置环境变量（Secrets）**：
   - 进入仓库 → Settings → Secrets and variables → Actions
   - 点击"New repository secret"
   - 添加以下环境变量：
     - `HUAWEI_USERNAME`：华为系统用户名
     - `HUAWEI_PASSWORD`：华为系统密码
     - `SEMS_USERNAME`：SEMS系统用户名
     - `SEMS_PASSWORD`：SEMS系统密码
     - `ESOLAR_USERNAME`：ESolar系统用户名
     - `ESOLAR_PASSWORD`：ESolar系统密码

### 2. 自动化工作流配置

工作流配置文件已创建：`.github/workflows/scrape-and-update-data.yml`

**工作流默认配置**：
- 每日UTC时间00:00（北京时间08:00）自动运行
- 支持手动触发：在Actions选项卡中选择"太阳能数据爬虫与更新"，点击"Run workflow"

**修改运行时间**：
如果需要修改自动运行时间，编辑`.github/workflows/scrape-and-update-data.yml`中的cron表达式：
```yaml
# 修改这里的cron表达式
- cron: '0 0 * * *'  # UTC时间每天00:00，北京时间08:00
```

cron格式说明：`分钟 小时 日期 月份 星期几`

### 3. 配置完成后

- GitHub Actions会按设定的时间自动运行爬虫脚本
- 脚本会爬取各系统的数据和截图，进行处理后更新到仓库
- 更新的数据和截图可以用于网站展示

## 项目结构说明

- `update_solar_dashboard.py`：主程序，协调各爬虫的运行
- `huawei_scraper.py`：华为系统爬虫
- `sems_combined_tool.py`：SEMS系统爬虫
- `esolar_scraper.py`：ESolar系统爬虫
- `screenshots/`：存储爬取的截图
- `data/`：存储历史数据
- `index.html`：前端展示页面

## 技术细节

### 截图裁剪功能

脚本自动对各项目的截图进行裁剪处理：
- 项目1和2：先从顶部裁剪到260像素高度，再从底部裁剪到195像素高度
- 项目3和4：先从顶部裁剪到225像素高度，再从底部裁剪到180像素高度

### CI环境适配

所有爬虫脚本已适配GitHub Actions环境：
- 支持无头模式运行
- 自动检测和使用系统PATH中的浏览器驱动
- 添加了必要的兼容性参数

## 本地测试

如果需要在本地测试脚本，可以直接运行：

```bash
python update_solar_dashboard.py
```

本地运行时会使用代码中默认的用户名和密码（如果未设置环境变量）。

## 常见问题

### 工作流执行失败

1. 检查环境变量（Secrets）是否正确设置
2. 查看工作流日志，排查具体错误原因
3. 确保GitHub Actions有足够的权限推送代码（默认已配置）

### 截图质量问题

如果截图质量不佳，可以调整爬虫脚本中的相关参数，如浏览器窗口大小、等待时间等。

### 定时更新时间

默认在北京时间早上8点更新数据。如需调整，请修改工作流文件中的cron表达式。

## 注意事项

- 请妥善保管您的系统账号密码，避免泄露
- 定期检查工作流运行状态，确保数据正常更新
- 如遇网站更新导致爬虫失效，请及时更新爬虫脚本