import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
  },
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '实时监控大屏' },
      },
      {
        path: 'persons',
        name: 'Persons',
        component: () => import('@/views/Persons.vue'),
        meta: { title: '人员人脸档案' },
      },
      {
        path: 'devices',
        name: 'Devices',
        component: () => import('@/views/Devices.vue'),
        meta: { title: '识别通道管理' },
      },
      {
        path: 'events',
        name: 'Events',
        component: () => import('@/views/Events.vue'),
        meta: { title: '识别记录审计' },
      },
      {
        path: 'testbench',
        name: 'Testbench',
        component: () => import('@/views/Testbench.vue'),
        meta: { title: '算法测试台' },
      },
      {
        path: 'config',
        name: 'Config',
        component: () => import('@/views/Config.vue'),
        meta: { title: '识别参数与模型升级' },
      },
      {
        path: 'api-docs',
        name: 'ApiDocs',
        component: () => import('@/views/ApiDocs.vue'),
        meta: { title: '接口调用说明' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('access_token')
  if (to.path !== '/login' && !token) {
    next('/login')
  } else {
    next()
  }
})

export default router
