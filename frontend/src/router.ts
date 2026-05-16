import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import HealthPage from './pages/HealthPage.vue'
import ReviewPage from './pages/ReviewPage.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'health', component: HealthPage },
  { path: '/review', name: 'review', component: ReviewPage },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
