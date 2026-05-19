import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import HealthPage from './pages/HealthPage.vue'
import HistoryDetailPage from './pages/HistoryDetailPage.vue'
import HistoryPage from './pages/HistoryPage.vue'
import ReposPage from './pages/ReposPage.vue'
import ReviewPage from './pages/ReviewPage.vue'
import SettingsPage from './pages/SettingsPage.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/review' },
  { path: '/review', name: 'review', component: ReviewPage },
  { path: '/repos', name: 'repos', component: ReposPage },
  { path: '/history', name: 'history', component: HistoryPage },
  { path: '/history/:runId', name: 'history-detail', component: HistoryDetailPage, props: true },
  { path: '/settings', name: 'settings', component: SettingsPage },
  { path: '/status', name: 'health', component: HealthPage },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
