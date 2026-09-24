import path from 'node:path'
import { defineConfig } from 'vitepress'

const REPO = 'https://github.com/lance2016/ai-is-simple'
const ROOT = path.resolve(__dirname, '..')

// Markdown files that live in the repo but are not course pages.
const NOT_PAGES = ['Agents.md', 'STYLE_GUIDE.md', 'SOURCES.md']

// Relative links to code files or non-page docs have no page on the site,
// so point them at GitHub instead of producing dead links.
function githubLinks(md) {
  md.core.ruler.push('github_links', (state) => {
    // Some renders (e.g. page titles) carry no file path; nothing to rewrite there.
    if (!state.env.path) return
    const fromDir = path.dirname(path.relative(ROOT, state.env.path))
    for (const block of state.tokens) {
      for (const token of block.children ?? []) {
        if (token.type !== 'link_open') continue
        const href = token.attrGet('href')
        if (!href || /^([a-z]+:|#|\/)/i.test(href)) continue
        const target = path.posix.join(fromDir, href.split('#')[0])
        const ext = path.extname(target)
        const isPage = ext === '' || (ext === '.md' && !NOT_PAGES.includes(target))
        if (!isPage) token.attrSet('href', `${REPO}/blob/main/${target}`)
      }
    }
  })
}

export default defineConfig({
  lang: 'zh-CN',
  title: 'AI 如此简单',
  description: '一张图 + 一句话 + 一小段代码，把一个 AI Agent 概念讲明白',
  base: '/ai-is-simple/',

  // The README files stay the single source of content; they only get
  // renamed to index pages. The root README is the site home.
  rewrites: {
    'README.md': 'index.md',
    'chapters/:dir/README.md': 'chapters/:dir/index.md',
    'labs/:dir/README.md': 'labs/:dir/index.md',
  },
  srcExclude: [
    ...NOT_PAGES,
    '**/skills/**',
    '**/demo/**',
    '**/notes/**',
    '.venv/**',
  ],

  markdown: {
    config: githubLinks,
    languageAlias: { env: 'dotenv' },
  },

  themeConfig: {
    // No top nav: the sidebar is the only course navigation.
    // Order follows the README reading advice: main line first (00-03, 15),
    // so prev/next walks readers through it before the optional chapters.
    sidebar: [
      { text: '项目介绍', link: '/' },
      {
        text: '主线课程',
        items: [
          { text: '00 · Chat Completion', link: '/chapters/00-chat-completion/' },
          { text: '01 · Agent Loop', link: '/chapters/01-agent-loop/' },
          { text: '02 · Tool Use', link: '/chapters/02-tool-use/' },
          { text: '03 · Permission', link: '/chapters/03-permission/' },
          { text: '15 · Agent Harness', link: '/chapters/15-integrated-harness/' },
        ],
      },
      {
        text: '按需能力',
        items: [
          { text: '04 · Hooks', link: '/chapters/04-hooks/' },
          { text: '05 · Planning', link: '/chapters/05-planning/' },
          { text: '06 · Subagents', link: '/chapters/06-subagents/' },
          { text: '07 · Skills', link: '/chapters/07-skill-loading/' },
          { text: '08 · Context', link: '/chapters/08-context-compact/' },
          { text: '09 · Memory', link: '/chapters/09-memory/' },
          { text: '10 · Tasks', link: '/chapters/10-tasks/' },
          { text: '11 · Background Tasks', link: '/chapters/11-background-tasks/' },
          { text: '12 · Cron', link: '/chapters/12-cron-scheduler/' },
          { text: '13 · Agent Teams', link: '/chapters/13-agent-teams/' },
          { text: '14 · MCP', link: '/chapters/14-mcp-plugin/' },
          { text: '16 · Workflow Runtime', link: '/chapters/16-workflow-runtime/' },
          { text: '17 · Goal Loop', link: '/chapters/17-goal-loop/' },
        ],
      },
      {
        text: '实战',
        items: [
          { text: 'Lab 01 · Coding Agent 搭建', link: '/labs/01-mini-coding-agent/' },
          { text: 'Lab 02 · 长期记忆', link: '/labs/02-memory/' },
          { text: 'Lab 03 · 子 Agent 任务委派', link: '/labs/03-subagent/' },
          { text: 'Lab 04 · MCP 工具接入', link: '/labs/04-mcp/' },
          { text: 'Lab 05 · Hooks：代码验收', link: '/labs/05-verify/' },
          { text: 'Lab 06 · Agent 可观测性', link: '/labs/06-observability/' },
          { text: 'Lab 07 · 上下文管理', link: '/labs/07-context-management/' },
          { text: 'Lab 08 · Agent 效果评估', link: '/labs/08-evaluation/' },
        ],
      },
    ],

    outline: { level: [2, 3], label: '本页目录' },
    docFooter: { prev: '上一章', next: '下一章' },
    socialLinks: [{ icon: 'github', link: REPO }],
    editLink: {
      pattern: `${REPO}/edit/main/:path`,
      text: '在 GitHub 上修改此页',
    },

    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: '搜索', buttonAriaLabel: '搜索' },
          modal: {
            noResultsText: '没有找到结果',
            resetButtonTitle: '清空',
            footer: { selectText: '选择', navigateText: '切换', closeText: '关闭' },
          },
        },
      },
    },

    darkModeSwitchLabel: '外观',
    lightModeSwitchTitle: '切换到浅色',
    darkModeSwitchTitle: '切换到深色',
    sidebarMenuLabel: '目录',
    returnToTopLabel: '回到顶部',
    notFound: { title: '页面不存在', quote: '这一页还没写。', linkText: '回到首页' },
  },
})
