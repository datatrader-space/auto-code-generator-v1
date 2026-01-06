<template>
  <div class="agent-playground h-screen flex flex-col bg-gray-100 overflow-hidden">

    <!-- Top Bar: Agent Info (hidden in fullscreen) -->
    <div v-if="!isFullscreen" class="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-4 shrink-0 shadow-sm z-10">
        <div class="flex items-center gap-4">
            <button @click="$router.push('/agents')" class="text-gray-500 hover:text-gray-700">
                ← Back
            </button>
            <div class="h-6 w-px bg-gray-200"></div>
            <h1 class="text-lg font-bold text-gray-800">
                {{ agent.id ? agent.name || 'Edit Agent' : 'New Agent' }}
            </h1>
        </div>
    </div>

    <!-- Main Workspace -->
    <div class="flex-1 flex overflow-hidden">

        <!-- Left: Builder (Collapsible & Resizable) -->
        <div
            v-if="showBuilder && !isFullscreen"
            :style="{ width: builderWidth + 'px' }"
            class="border-r border-gray-200 overflow-hidden flex-shrink-0 relative"
        >
            <AgentBuilder
                v-if="agent"
                v-model:agent="agent"
                :isSaving="saving"
                @save="saveAgent"
            />

            <!-- Resize Handle -->
            <div
                @mousedown="startResize"
                class="absolute top-0 right-0 w-1 h-full cursor-ew-resize hover:bg-blue-400 bg-gray-300 transition-colors z-20"
                title="Drag to resize"
            ></div>
        </div>

        <!-- Right: Preview / Chat -->
        <div class="flex-1 flex flex-col bg-white relative" :class="{ 'fixed inset-0 z-50': isFullscreen }">
            <div class="p-2 border-b border-gray-100 bg-gray-50 flex items-center justify-between text-xs font-mono">
                <!-- Left: View Controls -->
                <div class="flex gap-2">
                    <button
                        v-if="!isFullscreen"
                        @click="showBuilder = !showBuilder"
                        class="px-2 py-1 rounded bg-gray-200 hover:bg-gray-300 text-gray-700 transition flex items-center gap-1"
                        :title="showBuilder ? 'Hide Builder' : 'Show Builder'"
                    >
                        {{ showBuilder ? '◀ Hide' : '▶ Show' }} Builder
                    </button>
                    <button
                        @click="isFullscreen = !isFullscreen"
                        class="px-2 py-1 rounded bg-gray-200 hover:bg-gray-300 text-gray-700 transition flex items-center gap-1"
                        :title="isFullscreen ? 'Exit Fullscreen' : 'Fullscreen Chat'"
                    >
                        {{ isFullscreen ? '⊗ Exit' : '⛶ Fullscreen' }}
                    </button>
                </div>

                <!-- Center: Tabs -->
                <div class="flex gap-4">
                    <button
                        @click="activeTab = 'chat'"
                        :class="activeTab === 'chat' ? 'text-blue-600 font-bold border-b-2 border-blue-600' : 'text-gray-400 hover:text-gray-600'"
                    >
                        PREVIEW SESSION
                    </button>
                    <button
                        @click="activeTab = 'knowledge'"
                        :class="activeTab === 'knowledge' ? 'text-blue-600 font-bold border-b-2 border-blue-600' : 'text-gray-400 hover:text-gray-600'"
                    >
                        KNOWLEDGE CONTEXT
                    </button>
                    <button
                        @click="activeTab = 'trace'"
                        :class="activeTab === 'trace' ? 'text-blue-600 font-bold border-b-2 border-blue-600' : 'text-gray-400 hover:text-gray-600'"
                    >
                        TRACE
                    </button>
                </div>

                <!-- Right: Spacer for balance -->
                <div class="w-32"></div>
            </div>
            
            <!-- Trace Tab -->
            <div v-if="activeTab === 'trace'" class="flex-1 overflow-hidden flex flex-col items-center justify-center">
                 <SessionTrace v-if="activeSessionId" :session-id="activeSessionId" class="w-full h-full" />
                 <div v-else class="text-gray-400">
                    <div class="text-4xl mb-2 text-center">🔍</div>
                    <p>Start a session to view trace details.</p>
                 </div>
            </div>
            
            
            <!-- Chat Interface (Always Active) -->
            <div v-if="activeTab === 'chat'" class="flex-1 flex flex-col overflow-hidden">
                <!-- Feed -->
                <div class="flex-1 overflow-y-auto px-3 py-2 bg-gray-50" ref="feed">
                    <div v-if="chatEvents.length === 0" class="flex flex-col items-center justify-center h-full text-gray-400">
                        <div class="text-4xl mb-2">✨</div>
                        <p>Agent {{ agent.name }} is ready.</p>
                    </div>

                    <div v-for="event in chatEvents" :key="event.id" class="mb-2 w-full">
                        <!-- User -->
                        <div v-if="event.type === 'user'" class="bg-blue-600 text-white p-3 rounded-xl rounded-br-sm max-w-[85%] ml-auto shadow-sm">
                            {{ event.content }}
                        </div>

                        <!-- Assistant -->
                        <div v-if="event.type === 'assistant'" class="bg-white border border-gray-200 p-3 rounded-xl rounded-bl-sm max-w-[85%] mr-auto shadow-sm prose prose-sm" v-html="formatMarkdown(event.content)">
                        </div>

                        <!-- Tool Call -->
                        <div v-if="event.type === 'tool_call'" class="border-l-4 border-amber-500 bg-amber-50 p-2 my-2 rounded text-sm">
                            <div class="font-bold text-amber-800 flex items-center gap-2">
                                🛠️ Using Tool: {{ event.data.tool }}
                            </div>
                            <div class="font-mono text-xs mt-1 bg-amber-100/50 p-1 rounded whitespace-pre-wrap">{{ event.data.params }}</div>
                        </div>

                        <!-- Tool Result -->
                        <div v-if="event.type === 'tool_result'" class="border-l-4 border-purple-500 bg-purple-50 p-2 my-2 rounded text-sm">
                            <div class="font-bold text-purple-800">
                                📄 Tool Result: {{ event.data.tool_name }}
                            </div>
                            <div class="font-mono text-xs mt-1 bg-white p-1 rounded max-h-40 overflow-y-auto">{{ formatToolResult(event.data.result) }}</div>
                        </div>

                        <!-- Thought -->
                        <div v-if="event.type === 'thought'" class="border-l-4 border-purple-400 bg-purple-50/50 p-2 my-2 rounded text-xs text-purple-700 italic">
                             🤔 {{ event.data.content }}
                        </div>

                         <!-- Error -->
                        <div v-if="event.type === 'error'" class="border-l-4 border-red-500 bg-red-50 p-3 my-2 rounded text-red-700 text-sm flex items-center gap-2">
                            <span>❌</span> {{ event.data.message }}
                        </div>
                    </div>
                </div>

                <!-- Input -->
                <div class="p-3 bg-white border-t border-gray-200">
                    <div class="flex gap-2">
                        <textarea
                            v-model="userMessage"
                            placeholder="Chat with agent..."
                            class="flex-1 p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
                            :class="isFullscreen ? 'h-20' : 'h-14'"
                            @keydown.enter.prevent="sendMessage"
                            :disabled="isProcessing"
                        ></textarea>
                        <button
                            @click="sendMessage"
                            :disabled="!userMessage.trim() || isProcessing"
                            class="px-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 font-medium shrink-0 transition"
                        >
                            {{ isProcessing ? '⏳' : 'Send' }}
                        </button>
                    </div>
                </div>
            </div>

            <!-- Knowledge Interface -->
            <div v-if="activeTab === 'knowledge'" class="flex-1 flex overflow-hidden">
                <!-- Doc List -->
                <div class="w-1/3 border-r border-gray-200 overflow-y-auto bg-gray-50">
                    <div v-if="loadingDocs" class="p-4 text-center text-gray-500 text-sm">Loading docs...</div>
                    <div v-else-if="knowledgeDocs.length === 0" class="p-4 text-center text-gray-500 text-sm">
                        No knowledge documents found for this repository.
                    </div>
                    <div v-else>
                        <div 
                            v-for="doc in knowledgeDocs" 
                            :key="doc.spec_id"
                            @click="selectDoc(doc)"
                            :class="['p-3 border-b border-gray-100 cursor-pointer hover:bg-white transition', selectedDoc?.spec_id === doc.spec_id ? 'bg-white border-l-4 border-l-blue-500' : '']"
                        >
                            <div class="text-sm font-bold text-gray-700 truncate">{{ doc.title || doc.spec_id }}</div>
                            <div class="text-xs text-gray-500">{{ doc.kind }}</div>
                        </div>
                    </div>
                </div>

                <!-- Doc View & Analysis -->
                <div class="flex-1 overflow-y-auto p-6">
                    <div v-if="!selectedDoc" class="flex items-center justify-center h-full text-gray-400">
                        <p>Select a document to view analysis.</p>
                    </div>
                    <div v-else class="space-y-6">
                        <!-- AI Analysis -->
                         <div class="bg-indigo-50 border border-indigo-100 rounded-lg p-4">
                            <h3 class="text-sm font-bold text-indigo-800 mb-2 flex items-center gap-2">
                                🤖 AI Analysis
                                <span v-if="analyzingDoc" class="text-xs font-normal text-indigo-500">(Generating...)</span>
                            </h3>
                            <div v-if="analyzingDoc" class="animate-pulse space-y-2">
                                <div class="h-4 bg-indigo-100 rounded w-3/4"></div>
                                <div class="h-4 bg-indigo-100 rounded w-1/2"></div>
                            </div>
                            <div v-else-if="docAnalysis" class="prose prose-sm text-indigo-900" v-html="formatMarkdown(docAnalysis)"></div>
                            <div v-else class="text-xs text-indigo-400 italic">Select a document to generate analysis.</div>
                        </div>

                        <!-- Raw Content -->
                        <div>
                             <h3 class="text-sm font-bold text-gray-800 mb-2">Original Content</h3>
                             <div class="bg-gray-50 p-4 rounded border border-gray-200 font-mono text-xs whitespace-pre-wrap overflow-x-auto">
                                {{ selectedDoc.content }}
                             </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, onBeforeUnmount, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { marked } from 'marked';
import api from '../services/api';
import AgentBuilder from '../components/AgentBuilder.vue';
import SessionTrace from '../components/SessionTrace.vue';

const route = useRoute();
const router = useRouter();

const agent = ref({
    name: 'New Agent',
    description: '',
    system_prompt_template: 'You are a helpful AI assistant enabled with tools.',
    knowledge_scope: 'system',
    tool_ids: [],
    temperature: 0.7
});

const saving = ref(false);
const systems = ref([]);
const repositories = ref([]);
// New: LLM Models
const llmModels = ref([]);
const selectedContext = ref({ system: null, repo: null, model: null });
const activeSessionId = ref(null); // This is actually conversation_id in the new backend logic
const chatEvents = ref([]);
const userMessage = ref('');
const isProcessing = ref(false);
const activeTab = ref('chat');
const knowledgeDocs = ref([]);
const loadingDocs = ref(false);
const selectedDoc = ref(null);
const analyzingDoc = ref(false);
const docAnalysis = ref('');
const showBuilder = ref(true); // Toggle builder visibility
const isFullscreen = ref(false); // Fullscreen chat mode
const builderWidth = ref(400); // Resizable builder width
let ws = null;

const fetchContextData = async () => {
    try {
        const [sysRes, modelRes] = await Promise.all([
            api.getSystems(),
            api.getLlmModels()
        ]);
        systems.value = sysRes.data.results || sysRes.data;
        llmModels.value = modelRes.data.results || modelRes.data;
    } catch (e) {
        console.error("Context load failed", e);
    }
};

// Consolidated repository logic
const fetchRepositories = async (systemId) => {
    if (!systemId) {
        repositories.value = [];
        return;
    }
    try {
        const res = await api.getRepositories(systemId);
        repositories.value = res.data.results || res.data;
    } catch (e) {
        console.error("Failed to load repositories", e);
    }
};

watch(() => selectedContext.value.system, (newSysId) => {
    // Only reset if we are NOT in the middle of a restore (heuristic: if repo is verified?)
    // Actually, just let it reset, then fetchLastConversation re-sets it.
    // However, Vue watcher runs synchronously. 
    // If I set system, this runs: sets repo=null.
    // Then I set repo=saved.
    // It works fine.
    if (repositories.value.length > 0 && repositories.value[0].system !== newSysId) {
         selectedContext.value.repo = null;
    }
    fetchRepositories(newSysId);
    knowledgeDocs.value = [];
    selectedDoc.value = null;
});

const fetchLastConversation = async () => {
    if (!agent.value.id) return;
    try {
        const res = await api.getConversations({
            agent_profile_id: agent.value.id,
            ordering: '-updated_at',
            limit: 1
        });
        
        if (res.data.results && res.data.results.length > 0) {
            let lastConv = res.data.results[0];
            
            // If list view didn't include messages, fetch full details
            if (!lastConv.messages || lastConv.messages.length === 0) {
                try {
                    const detailRes = await api.getConversation(lastConv.id);
                    lastConv = detailRes.data;
                    console.log("Fetched detailed conversation:", lastConv);
                } catch (err) {
                    console.error("Failed to fetch conversation details", err);
                }
            }

            activeSessionId.value = lastConv.id;
            
            // Restore context
            if (lastConv.system) {
                // Set system. Watcher will trigger and clear repo.
                selectedContext.value.system = lastConv.system;
                
                // Fetch repos explicitly to ensure data availability for UI
                await fetchRepositories(lastConv.system);
                
                // Restore repo (overriding validation/watcher clear)
                selectedContext.value.repo = lastConv.repository;
            }
            selectedContext.value.model = lastConv.llm_model;
            
            // Restore chat history
            if (lastConv.messages) {
                 chatEvents.value = lastConv.messages.map(msg => ({
                     id: msg.id,
                     type: msg.role === 'user' ? 'user' : 'assistant', 
                     content: msg.content,
                     data: msg
                 }));
                 nextTick(scrollToBottom);
            }
            
            // Reconnect WS
            const repoId = lastConv.repository || '0';
            connectWebSocket(repoId);
        }
    } catch (e) {
        console.error("Failed to fetch last conversation", e);
    }
};

onMounted(async () => {
    const id = route.params.id;
    if (id !== 'new') {
        agent.value.id = id; // Set ID early
        await fetchAgent(id);
        await fetchContextData();
        await fetchLastConversation();
        
        // Auto-init chat session if none exists
        if (!activeSessionId.value && agent.value.id) {
            await initChatSession();
        }
    } else {
        await fetchContextData();
    }
});

const initChatSession = async () => {
    try {
        const res = await api.startAgentChat(agent.value.id, null); // No repository needed
        activeSessionId.value = res.data.conversation_id;
        // Use repository ID 0 for agent-only chat (no repo required)
        connectWebSocket(0);
    } catch (e) {
        console.error('Failed to initialize chat:', e);
    }
};

const loadKnowledge = async () => {
    activeTab.value = 'knowledge';
    if (!selectedContext.value.system || !selectedContext.value.repo) return;
    
    // Lazy load
    if (knowledgeDocs.value.length === 0) {
        try {
            loadingDocs.value = true;
            // Fetch docs of all kinds
            const res = await api.getKnowledgeDocs(selectedContext.value.system, selectedContext.value.repo);
            knowledgeDocs.value = res.data.docs || [];
        } catch (e) {
            console.error("Failed to load knowledge docs", e);
        } finally {
            loadingDocs.value = false;
        }
    }
};

const selectDoc = async (doc) => {
    selectedDoc.value = doc;
    docAnalysis.value = '';
    analyzingDoc.value = true;
    
    try {
        const res = await api.analyzeKnowledgeDoc(
            selectedContext.value.system,
            selectedContext.value.repo,
            doc.kind,
            doc.spec_id
        );
        docAnalysis.value = res.data.summary;
    } catch (e) {
        console.error("Analysis failed", e);
        docAnalysis.value = "Failed to generate analysis: " + str(e);
    } finally {
        analyzingDoc.value = false;
    }
};

const fetchAgent = async (id) => {
    try {
        const res = await api.get(`/agents/${id}/`);
        // Ensure tool_ids maps to tools objects if API returns expanded objects
        // The serializer expects tool_ids for write, but read might separate them
        const data = res.data;
        if (!data.tool_ids && data.tools) {
            data.tool_ids = data.tools.map(t => t.id);
        }
        agent.value = data;
    } catch (e) {
        console.error("Agent load failed", e);
    }
};

const saveAgent = async (agentData) => {
    try {
        saving.value = true;
        const dataToSave = agentData || agent.value;
        let res;
        if (dataToSave.id) {
            res = await api.patch(`/agents/${dataToSave.id}/`, dataToSave);
        } else {
            res = await api.post('/agents/', dataToSave);
            // Redirect to edit mode to prevent duplicate creates
            router.replace(`/agents/${res.data.id}`);
        }
        agent.value = res.data;
        // Fix up tool ids again if needed
        if (!agent.value.tool_ids && agent.value.tools) {
            agent.value.tool_ids = agent.value.tools.map(t => t.id);
        }
        return agent.value;
    } catch (e) {
        alert("Failed to save agent: " + (e.response?.data?.error || e.message));
        return null;
    } finally {
        saving.value = false;
    }
};

const formatMarkdown = (text) => marked(text || '');
const formatToolResult = (result) => {
    if (typeof result === 'object') return JSON.stringify(result, null, 2);
    return result;
};

// WebSocket Handler
const connectWebSocket = (repoId) => {
    if (ws) ws.close();
    
    // Connect to Repository Chat but using the conversation created by start_chat
    ws = new WebSocket(`ws://localhost:8000/ws/chat/repository/${repoId}/`);
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleChatEvent(data);
    };
    
    ws.onclose = () => console.log("WS Closed");
    ws.onerror = (e) => console.error("WS Error", e);
};

const handleChatEvent = (data) => {
    // Reuse logic from AgentRunnerDashboard
    if (data.type === 'assistant_message_chunk') {
         if (chatEvents.value.length > 0 && chatEvents.value[chatEvents.value.length - 1].type === 'assistant') {
             chatEvents.value[chatEvents.value.length - 1].content += data.chunk;
         } else {
             chatEvents.value.push({
                 id: Date.now(),
                 type: 'assistant',
                 content: data.chunk
             });
         }
         isProcessing.value = true; // Still streaming
    } else if (data.type === 'assistant_message_complete') {
         isProcessing.value = false;
         // Ensure full message
         if (chatEvents.value.length > 0 && chatEvents.value[chatEvents.value.length - 1].type === 'assistant') {
             chatEvents.value[chatEvents.value.length - 1].content = data.full_message;
         }
    } else if (data.type === 'tool_call' || data.type === 'agent_tool_call') {
         chatEvents.value.push({
            id: Date.now(),
            type: 'tool_call',
            data: { tool: data.tool, params: data.tool_input || data.params }
        });
        isProcessing.value = true;
    } else if (data.type === 'agent_step' || data.type === 'agent_step_start') {
        if (data.thought || data.action) {
             chatEvents.value.push({
                id: Date.now(),
                type: 'thought',
                data: { content: data.thought || data.action }
            });
        }
    } else if (data.type === 'tool_result' || data.type === 'agent_tool_result') {
        chatEvents.value.push({
            id: Date.now(),
            type: 'tool_result',
            data: { tool_name: data.tool_name, result: data.result }
        });
    } else if (data.type === 'error' || data.type === 'agent_error') {
        isProcessing.value = false;
         chatEvents.value.push({
            id: Date.now(),
            type: 'error',
            data: { message: data.error || data.message }
        });
    }

    scrollToBottom();
};

const sendMessage = () => {
    if (!userMessage.value.trim()) return;
    
    const content = userMessage.value;
    userMessage.value = '';
    isProcessing.value = true;
    
    // Add user message to UI
    chatEvents.value.push({
        id: Date.now(),
        type: 'user',
        content: content
    });
    scrollToBottom();
    
    // Send to WS
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: 'chat_message',
            message: content,
            conversation_id: activeSessionId.value // Must match the one created by start_chat
        }));
    } else {
        alert("Connection lost. Please restart session.");
        isProcessing.value = false;
    }
};

const scrollToBottom = () => {
    nextTick(() => {
        const feed = document.querySelector('.overflow-y-auto'); // Simple selector, ref would be better
        if (feed) feed.scrollTop = feed.scrollHeight;
    });
};

const runAgent = async () => {
    if (agent.value.knowledge_scope === 'system' && !selectedContext.value.system) {
        alert("Please select a System Context for this agent.");
        return;
    }
    
    // Repository is now optional (Free Agent mode)
    const repoId = selectedContext.value.repo;

    try {
        // Save first (auto-save behavior)
        if (!agent.value.id) {
            const saved = await saveAgent();
            if (!saved) return;
        } else {
            // Also save updates before run
            await saveAgent();
        }
        
        // Start Chat
        const res = await api.post(`/agents/${agent.value.id}/chat/`, {
            system_id: selectedContext.value.system,
            repository_id: repoId,
            llm_model_id: selectedContext.value.model
        });
        
        // Use conversation_id as the session ID
        activeSessionId.value = res.data.conversation_id || res.data.profile_id;
        chatEvents.value = []; // Clear previous events
        
        // Connect WS
        // If no repo, we need a way to chat. 
        // Currently WebSocket is /ws/chat/repository/:id/
        // We need a fallback or a generic chat WS for agents.
        // For now, if no repo, we might need to use a dummy ID or a new endpoint.
        // Let's assume backend handles '0' or 'none' or we need to update consumer routing.
        // Implementation Plan said: "If no repository is selected, ensure the consumer still functions (might need to relax get_repository logic)."
        // Let's use a special "agent" chat endpoint or assume repoId=0 works if backend logic allows.
        // Given current backend routing, let's use a dummy ID '0' and ensure backend handles it, 
        // OR better: use `ws/chat/agent/:conversation_id/` if possible?
        // The current consumers.py uses RepositoryChatConsumer mounted at /ws/chat/repository/<repo_id>/
        // We probably need to update routing.py or client side to use a "global" repo or system chat.
        // Let's use the repoId if exists, otherwise '0'.
        connectWebSocket(repoId || '0');
        
    } catch (e) {
        console.error(e);
        alert("Run failed: " + e.message);
    }
};

onBeforeUnmount(() => {
    if (ws) ws.close();
});

// Resize handler
const startResize = (e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = builderWidth.value;

    const doResize = (moveEvent) => {
        const delta = moveEvent.clientX - startX;
        const newWidth = Math.max(300, Math.min(800, startWidth + delta));
        builderWidth.value = newWidth;
    };

    const stopResize = () => {
        document.removeEventListener('mousemove', doResize);
        document.removeEventListener('mouseup', stopResize);
    };

    document.addEventListener('mousemove', doResize);
    document.addEventListener('mouseup', stopResize);
};

// Keyboard shortcuts
const handleKeyboard = (e) => {
    // Escape to exit fullscreen
    if (e.key === 'Escape' && isFullscreen.value) {
        isFullscreen.value = false;
    }
    // F11 to toggle fullscreen (prevent default browser fullscreen)
    if (e.key === 'F11') {
        e.preventDefault();
        isFullscreen.value = !isFullscreen.value;
    }
};

onMounted(() => {
    fetchContextData();
    if (route.params.id && route.params.id !== 'new') {
        fetchAgent(route.params.id);
    }
    // Add keyboard listeners
    document.addEventListener('keydown', handleKeyboard);
});

onBeforeUnmount(() => {
    document.removeEventListener('keydown', handleKeyboard);
});
</script>
