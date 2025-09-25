/**
 * 截图加载辅助工具
 * 用于加载和显示项目发电曲线截图
 */

/**
 * 查找并加载匹配的截图文件
 * @param {Array} paths - 可能的截图路径数组
 * @param {Function} onSuccess - 加载成功回调函数
 * @param {Function} onError - 加载失败回调函数
 */
function findAndLoadMatchingScreenshot(paths, onSuccess, onError) {
  if (!paths || paths.length === 0) {
    if (onError) onError('没有可用的截图路径');
    return;
  }

  const path = paths[0];
  const remainingPaths = paths.slice(1);

  // 检查是否是通配符路径
  if (path.includes('*')) {
    // 对于通配符路径，我们无法直接在客户端检查，
    // 所以我们尝试直接加载第一个可能的匹配项
    const img = new Image();
    img.onload = function() {
      onSuccess(img.src);
    };
    img.onerror = function() {
      // 如果加载失败，尝试下一个路径
      findAndLoadMatchingScreenshot(remainingPaths, onSuccess, onError);
    };
    // 使用当前时间戳防止缓存
    img.src = path.replace('*', '') + '?t=' + new Date().getTime();
  } else {
    // 对于普通路径，先检查文件是否存在
    const xhr = new XMLHttpRequest();
    xhr.open('HEAD', path, true);
    xhr.onload = function() {
      if (xhr.status === 200) {
        // 文件存在，加载它
        onSuccess(path);
      } else {
        // 文件不存在，尝试下一个路径
        findAndLoadMatchingScreenshot(remainingPaths, onSuccess, onError);
      }
    };
    xhr.onerror = function() {
      // 网络错误，尝试下一个路径
      findAndLoadMatchingScreenshot(remainingPaths, onSuccess, onError);
    };
    xhr.send();
  }
}

/**
 * 增强版发电曲线生成函数 - 用于黄河植物园项目
 * @param {number} projectId - 项目ID
 * @param {HTMLElement} img - 图片元素
 * @param {HTMLElement} svg - SVG元素
 * @returns {HTMLElement} - 包含发电曲线的容器元素
 */
function enhancedGeneratePowerCurveSVG(projectId, img, svg) {
  // 创建一个div容器来放置发电曲线
  if (!img && !svg) {
    const container = document.createElement('div');
    container.className = 'power-curve-container';
    return container;
  }

  // 根据项目ID设置不同的图片路径
  let screenshotPaths = [];
  if (projectId === 5) {
    // 黄河植物园项目 - 优先加载固定名称的截图
    screenshotPaths = [
      `screenshots/power_curve_5.png`,
      `screenshots/sems_element_goodwe-station-charts__chart_*.png`
    ];
  } else {
    // 其他项目使用原有命名规则
    screenshotPaths = [
      `screenshots/power_curve_${projectId}.png`,
      `screenshots/sems_screenshot_*.png`
    ];
  }

  // 尝试加载匹配的截图
  findAndLoadMatchingScreenshot(screenshotPaths, 
    function(successPath) {
      // 加载成功，显示图片，隐藏SVG
      if (img) {
        img.src = successPath + '?t=' + new Date().getTime();
        img.style.display = 'block';
      }
      if (svg) {
        svg.style.display = 'none';
      }
    },
    function(error) {
      // 加载失败，显示SVG回退方案
      if (img) {
        img.style.display = 'none';
      }
      if (svg) {
        svg.style.display = 'block';
      }
      console.log('无法加载发电曲线截图:', error);
    }
  );

  return null; // 如果提供了img和svg，不返回新容器
}

/**
 * 加载备选图片
 * @param {HTMLElement} imgElement - 图片元素
 * @param {number} projectId - 项目ID
 */
function loadFallbackImage(imgElement, projectId) {
  // 获取当前日期
  const today = new Date();
  const dateStr = today.toISOString().split('T')[0];
  
  // 根据项目ID生成备选图片路径
  const fallbackPaths = [
    `screenshots/power_curve_${projectId}.png`,
    `screenshots/power_curve_${projectId}_${dateStr}.png`,
    `screenshots/after_login_debug.png`
  ];
  
  // 尝试加载备选图片
  for (let i = 0; i < fallbackPaths.length; i++) {
    const fallbackImg = new Image();
    const timestamp = new Date().getTime();
    
    fallbackImg.onload = function() {
      imgElement.src = fallbackPaths[i] + '?t=' + timestamp;
      imgElement.style.display = 'block';
      console.log(`成功加载备选图片: ${fallbackPaths[i]}`);
    };
    
    fallbackImg.onerror = function() {
      // 只有当所有路径都失败时才隐藏图片
      if (i === fallbackPaths.length - 1) {
        imgElement.style.display = 'none';
        console.log(`所有备选图片加载失败，隐藏图片元素`);
      } else {
        console.log(`尝试下一个备选图片: ${fallbackPaths[i+1]}`);
      }
    };
    
    // 设置图片源，添加时间戳防止缓存
    fallbackImg.src = fallbackPaths[i] + '?t=' + timestamp;
  }
}