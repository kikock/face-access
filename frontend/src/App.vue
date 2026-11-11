<template>
  <router-view />
</template>

<style>
html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background-color: #f5f7fa;
}

/* 确保 Element Plus 全局大图预览弹窗始终最高层级置顶，不被表格或卡片遮挡 */
.el-image-viewer__wrapper {
  z-index: 99999 !important;
}
</style>

