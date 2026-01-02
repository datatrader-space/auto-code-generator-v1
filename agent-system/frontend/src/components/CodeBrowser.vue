<template>
  <div class="code-browser">
    <!-- Left Sidebar: File Tree -->
    <div class="sidebar" :style="{ width: sidebarWidth + 'px' }">
      <div class="sidebar-header">
        <div class="sidebar-tabs">
          <button 
            @click="sidebarTab = 'files'" 
            :class="{ active: sidebarTab === 'files' }"
            class="sidebar-tab">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
            Files
          </button>
          <button 
            @click="sidebarTab = 'artifacts'" 
            :class="{ active: sidebarTab === 'artifacts' }"
            class="sidebar-tab">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
            </svg>
            Artifacts
          </button>
        </div>
      </div>

      <div class="sidebar-content">
        <!-- File Tree -->
        <div v-if="sidebarTab === 'files'" class="file-tree">
          <div class="search-box">
            <input 
              v-model="fileSearch" 
              placeholder="Search files..."
              class="search-input" />
          </div>
          <div class="tree-list">
            <div v-if="loading" class="loading">Loading files...</div>
            <div v-else-if="!files.length" class="empty">No files found</div>
            <div v-else>
              <FileTreeNode 
                v-for="file in filteredFiles" 
                :key="file.path"
                :file="file"
                @select="openFile" />
            </div>
          </div>
        </div>

        <!-- Artifact Tree -->
        <div v-else class="artifact-tree">
          <div class="search-box">
            <input 
              v-model="artifactSearch" 
              placeholder="Search artifacts..."
              class="search-input" />
          </div>
          <div class="tree-list">
            <div v-if="!artifacts || !artifacts.length" class="empty">
              No artifacts available
            </div>
            <div v-else>
              <ArtifactTreeNode 
                v-for="artifact in filteredArtifacts" 
                :key="artifact.name"
                :artifact="artifact"
                @select="openArtifact" />
            </div>
          </div>
        </div>
      </div>

      <!-- Resize Handle -->
      <div class="resize-handle" @mousedown="startResize"></div>
    </div>

    <!-- Center: Editor Panel -->
    <div class="editor-panel">
      <!-- Tab Bar -->
      <div class="tab-bar" v-if="openTabs.length > 0">
        <div 
          v-for="tab in openTabs" 
          :key="tab.id"
          @click="activeTabId = tab.id"
          :class="['tab', { active: activeTabId === tab.id }]">
          <span class="tab-icon">{{ getFileIcon(tab.path) }}</span>
          <span class="tab-name">{{ tab.name }}</span>
          <button @click.stop="closeTab(tab.id)" class="tab-close">×</button>
        </div>
      </div>

      <!-- Monaco Editor -->
      <div class="editor-container">
        <MonacoEditor
          v-if="activeTab"
          :value="activeTab.content"
          :language="activeTab.language"
          :path="activeTab.path"
          :options="editorOptions"
          class="monaco-editor"
        />
        <div v-else class="empty-editor">
          <svg class="w-16 h-16 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p class="text-gray-500 font-medium">No file open</p>
          <p class="text-sm text-gray-400 mt-1">Select a file from the sidebar to view</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import MonacoEditor from 'monaco-editor-vue3'
import api from '../services/api'

const props = defineProps({
  repositoryId: {
    type: Number,
    required: true
  },
  systemId: {
    type: Number,
    required: true
  },
  artifacts: {
    type: Array,
    default: () => []
  }
})

// State
const sidebarTab = ref('files')
const sidebarWidth = ref(300)
const fileSearch = ref('')
const artifactSearch = ref('')
const files = ref([])
const loading = ref(false)
const openTabs = ref([])
const activeTabId = ref(null)

// Editor options
const editorOptions = {
  readOnly: true,
  minimap: { enabled: true },
  lineNumbers: 'on',
  scrollBeyondLastLine: false,
  automaticLayout: true,
  theme: 'vs-dark',
  fontSize: 14,
  wordWrap: 'on',
  folding: true,
  renderWhitespace: 'selection'
}

// Computed
const activeTab = computed(() => {
  return openTabs.value.find(t => t.id === activeTabId.value)
})

const filteredFiles = computed(() => {
  if (!files.value.length) return []
  
  // Build tree structure from flat file list
  const tree = buildFileTree(files.value, fileSearch.value)
  return tree
})

// Build hierarchical tree from flat file list
function buildFileTree(flatFiles, searchQuery = '') {
  const root = []
  const query = searchQuery.toLowerCase()
  
  // Filter files by search query first
  const filteredList = query 
    ? flatFiles.filter(f => f.path.toLowerCase().includes(query))
    : flatFiles
  
  // Group files by directory
  const dirMap = new Map()
  
  filteredList.forEach(file => {
    const parts = file.path.split('/')
    let currentPath = ''
    
    // Create directory nodes
    for (let i = 0; i < parts.length - 1; i++) {
      const parentPath = currentPath
      currentPath = currentPath ? `${currentPath}/${parts[i]}` : parts[i]
      
      if (!dirMap.has(currentPath)) {
        const dirNode = {
          name: parts[i],
          path: currentPath,
          type: 'directory',
          children: [],
          expanded: ref(false)  // Make expanded reactive
        }
        dirMap.set(currentPath, dirNode)
        
        // Add to parent or root
        if (parentPath && dirMap.has(parentPath)) {
          dirMap.get(parentPath).children.push(dirNode)
        } else if (!parentPath) {
          root.push(dirNode)
        }
      }
    }
    
    // Add file to its parent directory
    const fileName = parts[parts.length - 1]
    const parentPath = parts.slice(0, -1).join('/')
    const fileNode = {
      name: fileName,
      path: file.path,
      type: 'file',
      size: file.size
    }
    
    if (parentPath && dirMap.has(parentPath)) {
      dirMap.get(parentPath).children.push(fileNode)
    } else {
      root.push(fileNode)
    }
  })
  
  // Sort: directories first, then files, both alphabetically
  const sortNodes = (nodes) => {
    return nodes.sort((a, b) => {
      if (a.type === b.type) {
        return a.name.localeCompare(b.name)
      }
      return a.type === 'directory' ? -1 : 1
    })
  }
  
  // Recursively sort all levels
  const sortTree = (nodes) => {
    sortNodes(nodes)
    nodes.forEach(node => {
      if (node.children) {
        sortTree(node.children)
      }
    })
  }
  
  sortTree(root)
  return root
}

const filteredArtifacts = computed(() => {
  if (!artifactSearch.value) return props.artifacts
  const query = artifactSearch.value.toLowerCase()
  return props.artifacts.filter(a => 
    a.name.toLowerCase().includes(query) || 
    (a.type && a.type.toLowerCase().includes(query))
  )
})

// Methods
async function loadFiles() {
  loading.value = true
  console.log('🔍 Loading files for repo:', props.repositoryId, 'system:', props.systemId)
  try {
    const response = await api.getRepositoryFiles(props.systemId, props.repositoryId)
    console.log('📁 Files response:', response.data)
    files.value = response.data.files || []
    console.log('📁 Loaded', files.value.length, 'files')
  } catch (error) {
    console.error('❌ Failed to load files:', error)
    console.error('Error details:', error.response?.data)
    files.value = []
  } finally {
    loading.value = false
  }
}

async function openFile(filePath) {
  // Check if already open
  const existing = openTabs.value.find(t => t.path === filePath)
  if (existing) {
    activeTabId.value = existing.id
    return
  }

  try {
    // Load file content
    const response = await api.getFileContent(props.systemId, props.repositoryId, filePath)
    const content = response.data.content
    const language = detectLanguage(filePath)
    
    const newTab = {
      id: Date.now(),
      name: filePath.split('/').pop(),
      path: filePath,
      content,
      language,
      type: 'file'
    }
    
    openTabs.value.push(newTab)
    activeTabId.value = newTab.id
  } catch (error) {
    console.error('Failed to load file:', error)
    alert('Failed to load file: ' + error.message)
  }
}

function openArtifact(artifact) {
  // Check if already open
  const existing = openTabs.value.find(t => t.artifactId === artifact.name)
  if (existing) {
    activeTabId.value = existing.id
    return
  }

  const content = formatArtifactCode(artifact)
  const language = 'python' // Most artifacts are Python
  
  const newTab = {
    id: Date.now(),
    name: artifact.name,
    path: artifact.file || artifact.name,
    content,
    language,
    type: 'artifact',
    artifactId: artifact.name
  }
  
  openTabs.value.push(newTab)
  activeTabId.value = newTab.id
}

function closeTab(tabId) {
  const index = openTabs.value.findIndex(t => t.id === tabId)
  if (index === -1) return
  
  openTabs.value.splice(index, 1)
  
  // Switch to another tab if closing active tab
  if (activeTabId.value === tabId) {
    if (openTabs.value.length > 0) {
      activeTabId.value = openTabs.value[Math.max(0, index - 1)].id
    } else {
      activeTabId.value = null
    }
  }
}

function detectLanguage(filePath) {
  const ext = filePath.split('.').pop().toLowerCase()
  const langMap = {
    'py': 'python',
    'js': 'javascript',
    'vue': 'html',
    'ts': 'typescript',
    'tsx': 'typescript',
    'jsx': 'javascript',
    'json': 'json',
    'md': 'markdown',
    'html': 'html',
    'css': 'css',
    'scss': 'scss',
    'yaml': 'yaml',
    'yml': 'yaml',
    'xml': 'xml',
    'sql': 'sql',
    'sh': 'shell',
    'bash': 'shell'
  }
  return langMap[ext] || 'plaintext'
}

function formatArtifactCode(artifact) {
  // Try different fields for code content
  if (artifact.content) return artifact.content
  if (artifact.source_code) return artifact.source_code
  if (artifact.code) return artifact.code
  
  // Fallback to JSON
  return JSON.stringify(artifact, null, 2)
}

function getFileIcon(path) {
  const ext = path.split('.').pop().toLowerCase()
  const icons = {
    'py': '🐍',
    'js': '📜',
    'vue': '💚',
    'json': '📋',
    'md': '📝',
    'html': '🌐',
    'css': '🎨',
    'ts': '📘',
    'yaml': '⚙️',
    'sql': '🗄️'
  }
  return icons[ext] || '📄'
}

// Sidebar resize
let isResizing = false
function startResize(e) {
  isResizing = true
  document.addEventListener('mousemove', handleResize)
  document.addEventListener('mouseup', stopResize)
}

function handleResize(e) {
  if (!isResizing) return
  const newWidth = e.clientX
  if (newWidth >= 200 && newWidth <= 600) {
    sidebarWidth.value = newWidth
  }
}

function stopResize() {
  isResizing = false
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
}

// Lifecycle
onMounted(() => {
  console.log('🎨 CodeBrowser mounted')
  console.log('📦 Artifacts prop:', props.artifacts)
  console.log('📦 Artifacts count:', props.artifacts?.length || 0)
  loadFiles()
})

// Tree node component with directory support
import { h } from 'vue'

const FileTreeNode = {
  props: ['file', 'level'],
  emits: ['select'],
  setup(props, { emit }) {
    const getIcon = () => {
      if (props.file.type === 'directory') {
        const isExpanded = props.file.expanded?.value || false
        return isExpanded ? '📂' : '📁'
      }
      const ext = (props.file.path || '').split('.').pop().toLowerCase()
      const iconMap = {
        'py': '🐍',
        'js': '📜',
        'vue': '💚',
        'json': '📋',
        'md': '📝',
        'html': '🌐',
        'css': '🎨',
        'ts': '📘',
        'txt': '📄',
        'yml': '⚙️',
        'yaml': '⚙️'
      }
      return iconMap[ext] || '📄'
    }
    
    const handleClick = () => {
      if (props.file.type === 'directory') {
        if (props.file.expanded) {
          props.file.expanded.value = !props.file.expanded.value
        }
      } else {
        emit('select', props.file.path)
      }
    }
    
    const renderChildren = () => {
      if (props.file.type === 'directory' && props.file.expanded?.value && props.file.children) {
        return props.file.children.map(child =>
          h(FileTreeNode, {
            key: child.path,
            file: child,
            level: (props.level || 0) + 1,
            onSelect: (path) => emit('select', path)
          })
        )
      }
      return []
    }
    
    return () => h('div', {}, [
      h('div', {
        class: 'tree-node',
        style: { paddingLeft: `${(props.level || 0) * 12}px` },
        onClick: handleClick
      }, [
        props.file.type === 'directory' 
          ? h('span', { class: 'node-expand' }, props.file.expanded?.value ? '▼' : '▶')
          : h('span', { class: 'node-expand' }),
        h('span', { class: 'node-icon' }, getIcon()),
        h('span', { class: 'node-name' }, props.file.name)
      ]),
      ...renderChildren()
    ])
  }
}

const ArtifactTreeNode = {
  props: ['artifact'],
  emits: ['select'],
  setup(props, { emit }) {
    const getIcon = () => {
      const type = (props.artifact.type || '').toLowerCase()
      if (type.includes('model')) return '🗃️'
      if (type.includes('view')) return '👁️'
      if (type.includes('serializer')) return '📦'
      return '📄'
    }
    
    return () => h('div', {
      class: 'tree-node',
      onClick: () => emit('select', props.artifact)
    }, [
      h('span', { class: 'node-icon' }, getIcon()),
      h('span', { class: 'node-name' }, props.artifact.name),
      h('span', { class: 'node-type' }, props.artifact.type)
    ])
  }
}
</script>

<style scoped>
.code-browser {
  display: flex;
  height: 100%;
  background: #1e1e1e;
  color: #d4d4d4;
}

/* Sidebar */
.sidebar {
  position: relative;
  border-right: 1px solid #3c3c3c;
  display: flex;
  flex-direction: column;
  background: #252526;
}

.sidebar-header {
  border-bottom: 1px solid #3c3c3c;
}

.sidebar-tabs {
  display: flex;
}

.sidebar-tab {
  flex: 1;
  padding: 10px;
  background: transparent;
  color: #969696;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
  transition: all 0.2s;
}

.sidebar-tab:hover {
  background: #2a2d2e;
}

.sidebar-tab.active {
  background: #1e1e1e;
  color: #ffffff;
  border-bottom: 2px solid #007acc;
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
}

.search-box {
  padding: 8px;
  border-bottom: 1px solid #3c3c3c;
}

.search-input {
  width: 100%;
  padding: 6px 10px;
  background: #3c3c3c;
  border: 1px solid #454545;
  border-radius: 4px;
  color: #d4d4d4;
  font-size: 13px;
}

.search-input:focus {
  outline: none;
  border-color: #007acc;
}

.tree-list {
  padding: 4px 0;
}

.tree-node {
  padding: 6px 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  transition: background 0.1s;
}

.tree-node:hover {
  background: #2a2d2e;
}

.node-icon {
  font-size: 14px;
  margin-right: 4px;
}

.node-expand {
  display: inline-block;
  width: 12px;
  font-size: 10px;
  color: #858585;
  margin-right: 4px;
}

.node-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-type {
  font-size: 11px;
  color: #858585;
  background: #3c3c3c;
  padding: 2px 6px;
  border-radius: 3px;
}

.loading, .empty {
  padding: 20px;
  text-align: center;
  color: #858585;
  font-size: 13px;
}

/* Resize Handle */
.resize-handle {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  cursor: ew-resize;
  background: transparent;
}

.resize-handle:hover {
  background: #007acc;
}

/* Editor Panel */
.editor-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tab-bar {
  display: flex;
  background: #2d2d2d;
  border-bottom: 1px solid #3c3c3c;
  overflow-x: auto;
  overflow-y: hidden;
}

.tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #2d2d2d;
  color: #969696;
  border-right: 1px solid #3c3c3c;
  cursor: pointer;
  white-space: nowrap;
  font-size: 13px;
  transition: all 0.1s;
}

.tab:hover {
  background: #1e1e1e;
}

.tab.active {
  background: #1e1e1e;
  color: #ffffff;
  border-bottom: 2px solid #007acc;
}

.tab-icon {
  font-size: 14px;
}

.tab-name {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tab-close {
  background: none;
  border: none;
  color: #969696;
  cursor: pointer;
  font-size: 18px;
  padding: 0 4px;
  line-height: 1;
  transition: color 0.1s;
}

.tab-close:hover {
  color: #ffffff;
}

.editor-container {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.monaco-editor {
  width: 100%;
  height: 100%;
}

.empty-editor {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #858585;
}

/* Scrollbar styling */
.sidebar-content::-webkit-scrollbar,
.tab-bar::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.sidebar-content::-webkit-scrollbar-track,
.tab-bar::-webkit-scrollbar-track {
  background: #1e1e1e;
}

.sidebar-content::-webkit-scrollbar-thumb,
.tab-bar::-webkit-scrollbar-thumb {
  background: #424242;
  border-radius: 5px;
}

.sidebar-content::-webkit-scrollbar-thumb:hover,
.tab-bar::-webkit-scrollbar-thumb:hover {
  background: #4e4e4e;
}
</style>
