import { createApp } from 'vue'

import './styles/globals.css'
import './styles/tokens.css'

import App from './App.vue'
import { router } from './router'

createApp(App).use(router).mount('#app')
