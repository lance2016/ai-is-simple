import DefaultTheme from 'vitepress/theme'
import mediumZoom from 'medium-zoom'
import { nextTick, onMounted, watch } from 'vue'
import { useRoute } from 'vitepress'
import 'lxgw-wenkai-webfont/lxgwwenkai-bold.css'
import './style.css'

export default {
  extends: DefaultTheme,
  setup() {
    const route = useRoute()
    // Re-bind after each client-side navigation, since page images are replaced.
    const bindZoom = () => mediumZoom('.vp-doc img', { background: 'var(--vp-c-bg)' })
    onMounted(bindZoom)
    watch(() => route.path, () => nextTick(bindZoom))
  },
}
