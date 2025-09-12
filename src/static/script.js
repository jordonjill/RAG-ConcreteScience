// Global state management
class AppState {
    constructor() {
        this.apiKey = localStorage.getItem('rag_api_key') || '';
        this.conversationId = null;
        this.isConnected = false;
        this.modelInfo = null;
        this.isSettingsOpen = false;
        this.messageHistory = [];
    }

    setApiKey(key) {
        this.apiKey = key;
        if (key) {
            localStorage.setItem('rag_api_key', key);
        } else {
            localStorage.removeItem('rag_api_key');
        }
        this.updateInputState();
    }

    updateInputState() {
        const messageInput = document.getElementById('messageInput');
        const sendBtn = document.getElementById('sendBtn');
        
        if (this.apiKey) {
            messageInput.disabled = false;
            messageInput.placeholder = 'Type your message here...';
            sendBtn.disabled = false;
        } else {
            messageInput.disabled = true;
            messageInput.placeholder = 'Enter your API key in settings first...';
            sendBtn.disabled = true;
        }
    }

    updateConnectionStatus(isConnected, message = '') {
        this.isConnected = isConnected;
        const statusIndicator = document.getElementById('statusIndicator');
        const statusDot = statusIndicator.querySelector('.status-dot');
        const statusText = statusIndicator.querySelector('.status-text');
        
        if (isConnected) {
            statusDot.classList.add('online');
            statusText.textContent = 'Connected';
        } else {
            statusDot.classList.remove('online');
            statusText.textContent = message || 'Disconnected';
        }
    }
}

// Initialize app state
const appState = new AppState();

// API service class
class APIService {
    constructor() {
        this.baseURL = window.location.origin;
    }

    async makeRequest(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${appState.apiKey}`
            }
        };

        const finalOptions = {
            ...defaultOptions,
            ...options,
            headers: {
                ...defaultOptions.headers,
                ...options.headers
            }
        };

        try {
            const response = await fetch(url, finalOptions);
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error(`API request failed for ${endpoint}:`, error);
            throw error;
        }
    }

    async checkHealth() {
        return await this.makeRequest('/health');
    }

    async sendMessage(query, conversationId = null) {
        return await this.makeRequest('/chat', {
            method: 'POST',
            body: JSON.stringify({
                query: query,
                conversation_id: conversationId
            })
        });
    }

    async sendStreamingMessage(query, conversationId = null, onChunk = null) {
        const url = `${this.baseURL}/chat`;
        const options = {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${appState.apiKey}`
            },
            body: JSON.stringify({
                query: query,
                conversation_id: conversationId
            })
        };

        try {
            const response = await fetch(url, options);
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                
                if (done) break;
                
                // Decode the chunk immediately
                const chunk = decoder.decode(value, { stream: true });
                buffer += chunk;
                
                // Process complete lines immediately
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep incomplete line in buffer
                
                for (const line of lines) {
                    if (line.trim() === '') continue;
                    
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (onChunk) {
                                // Call onChunk immediately for real-time processing
                                onChunk(data);
                            }
                        } catch (e) {
                            console.warn('Failed to parse SSE data:', e, 'Line:', line);
                        }
                    }
                }
                
                // Small delay to allow UI updates
                await new Promise(resolve => setTimeout(resolve, 1));
            }
        } catch (error) {
            console.error(`Streaming API request failed for /chat:`, error);
            throw error;
        }
    }

    async getConfig() {
        return await this.makeRequest('/config');
    }
}

// Initialize API service
const apiService = new APIService();

// UI management class
class UIManager {
    constructor() {
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.loadingIndicator = document.getElementById('loadingIndicator');
        this.streamingIndicator = document.getElementById('streamingIndicator');
        
        // Settings elements
        this.settingsBtn = document.getElementById('settingsBtn');
        this.settingsSidebar = document.getElementById('settingsSidebar');
        this.settingsOverlay = document.getElementById('settingsOverlay');
        this.closeSettings = document.getElementById('closeSettings');
        this.apiKeyInput = document.getElementById('apiKey');
        this.toggleApiKey = document.getElementById('toggleApiKey');
        this.saveSettings = document.getElementById('saveSettings');
        this.testConnection = document.getElementById('testConnection');
        
        this.initializeEventListeners();
        this.setupAutoResize();
    }

    initializeEventListeners() {
        // Send message events
        this.sendBtn.addEventListener('click', () => this.handleSendMessage());
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSendMessage();
            }
        });

        // Settings events
        this.settingsBtn.addEventListener('click', () => this.openSettings());
        this.closeSettings.addEventListener('click', () => this.closeSettingsPanel());
        this.settingsOverlay.addEventListener('click', () => this.closeSettingsPanel());
        
        // API key management
        this.toggleApiKey.addEventListener('click', () => this.toggleApiKeyVisibility());
        this.saveSettings.addEventListener('click', () => this.handleSaveSettings());
        this.testConnection.addEventListener('click', () => this.handleTestConnection());
        
        // Sample questions
        document.addEventListener('click', (e) => {
            if (e.target.closest('.sample-question')) {
                const question = e.target.closest('.sample-question').dataset.question;
                if (question && appState.apiKey) {
                    this.messageInput.value = question;
                    this.handleSendMessage();
                }
            }
        });

        // Load API key on startup only if it exists
        if (appState.apiKey) {
            this.apiKeyInput.value = appState.apiKey;
        } else {
            // Ensure the input is empty if no API key is stored
            this.apiKeyInput.value = '';
        }
    }

    setupAutoResize() {
        this.messageInput.addEventListener('input', (e) => {
            e.target.style.height = 'auto';
            e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
        });
    }

    showLoading(show = true) {
        if (show) {
            this.loadingIndicator.classList.add('show');
        } else {
            this.loadingIndicator.classList.remove('show');
        }
    }

    showStreaming(show = true) {
        if (show) {
            this.streamingIndicator.style.display = 'flex';
        } else {
            this.streamingIndicator.style.display = 'none';
        }
    }

    openSettings() {
        appState.isSettingsOpen = true;
        this.settingsSidebar.classList.add('open');
        this.settingsOverlay.classList.add('open');
        document.body.style.overflow = 'hidden';
    }

    closeSettingsPanel() {
        appState.isSettingsOpen = false;
        this.settingsSidebar.classList.remove('open');
        this.settingsOverlay.classList.remove('open');
        document.body.style.overflow = '';
    }

    toggleApiKeyVisibility() {
        const input = this.apiKeyInput;
        const icon = this.toggleApiKey.querySelector('i');
        
        if (input.type === 'password') {
            input.type = 'text';
            icon.className = 'fas fa-eye-slash';
        } else {
            input.type = 'password';
            icon.className = 'fas fa-eye';
        }
    }

    async handleSaveSettings() {
        const newApiKey = this.apiKeyInput.value.trim();
        
        if (newApiKey !== appState.apiKey) {
            appState.setApiKey(newApiKey);
            
            if (newApiKey) {
                // Test the new API key
                await this.handleTestConnection();
            } else {
                appState.updateConnectionStatus(false, 'No API key');
                this.updateModelInfo(null);
            }
        }
        
        this.showNotification('Settings saved successfully', 'success');
    }

    async handleTestConnection() {
        if (!appState.apiKey) {
            this.showNotification('Please enter an API key first', 'error');
            return;
        }

        this.showLoading(true);
        
        try {
            const healthData = await apiService.checkHealth();
            
            if (healthData.status === 'healthy') {
                appState.updateConnectionStatus(true);
                this.showNotification('Connection successful!', 'success');
                
                // Get model info
                try {
                    const configData = await apiService.getConfig();
                    this.updateModelInfo(configData);
                } catch (configError) {
                    console.warn('Could not fetch model info:', configError);
                }
            } else {
                appState.updateConnectionStatus(false, healthData.message);
                this.showNotification(`Connection failed: ${healthData.message}`, 'error');
            }
        } catch (error) {
            appState.updateConnectionStatus(false, 'Connection failed');
            this.showNotification(`Connection test failed: ${error.message}`, 'error');
        } finally {
            this.showLoading(false);
        }
    }

    updateModelInfo(configData) {
        const modelStatus = document.getElementById('modelStatus');
        const modelName = document.getElementById('modelName');
        
        if (configData) {
            modelStatus.textContent = 'Connected';
            modelName.textContent = configData.ollama_model || 'Unknown';
        } else {
            modelStatus.textContent = 'Not connected';
            modelName.textContent = '-';
        }
    }

    async handleSendMessage() {
        const message = this.messageInput.value.trim();
        
        if (!message || !appState.apiKey) return;

        // Clear input immediately
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';

        // Hide welcome message if it exists
        const welcomeMessage = this.chatMessages.querySelector('.welcome-message');
        if (welcomeMessage) {
            welcomeMessage.style.display = 'none';
        }

        // Add user message to chat
        this.addMessage('user', message);
        
        // Create assistant message placeholder for streaming
        const assistantMessageDiv = this.createStreamingMessage();
        
        // Show streaming indicator
        this.showStreaming(true);
        
        try {
            let fullResponse = '';
            let conversationId = null;
            let hasReceivedContent = false;
            
            await apiService.sendStreamingMessage(
                message, 
                appState.conversationId,
                (chunk) => {
                    if (chunk.type === 'content' && chunk.response_chunk) {
                        fullResponse += chunk.response_chunk;
                        hasReceivedContent = true;
                        this.updateStreamingMessage(assistantMessageDiv, fullResponse);
                    } else if (chunk.type === 'done') {
                        conversationId = chunk.conversation_id;
                        if (hasReceivedContent) {
                            this.finalizeStreamingMessage(assistantMessageDiv, fullResponse);
                        } else {
                            this.finalizeStreamingMessage(assistantMessageDiv, 'No response received from the server.');
                        }
                    } else if (chunk.type === 'error') {
                        this.finalizeStreamingMessage(assistantMessageDiv, chunk.response_chunk || 'An error occurred.', true);
                    }
                }
            );
            
            // Update conversation ID
            if (conversationId) {
                appState.conversationId = conversationId;
            }
            
            // Update connection status
            appState.updateConnectionStatus(true);
            
        } catch (error) {
            console.error('Send message error:', error);
            
            // Update the streaming message with error
            this.finalizeStreamingMessage(
                assistantMessageDiv, 
                `Sorry, I encountered an error: ${error.message}`, 
                true
            );
            
            // Update connection status
            if (error.message.includes('401') || error.message.includes('Invalid API key')) {
                appState.updateConnectionStatus(false, 'Invalid API key');
                this.showNotification('Invalid API key. Please check your settings.', 'error');
            } else {
                appState.updateConnectionStatus(false, 'Connection error');
            }
        } finally {
            this.showLoading(false);
            this.showStreaming(false);
        }
    }

    addMessage(sender, content, isError = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        
        if (sender === 'user') {
            avatarDiv.innerHTML = '<i class="fas fa-user"></i>';
        } else {
            avatarDiv.innerHTML = '<i class="fas fa-robot"></i>';
        }
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const bubbleDiv = document.createElement('div');
        bubbleDiv.className = 'message-bubble';
        
        if (isError) {
            bubbleDiv.style.color = '#ff4757';
            bubbleDiv.style.borderColor = '#ff4757';
        }
        
        // Format the content (handle basic formatting)
        bubbleDiv.innerHTML = this.formatMessageContent(content);
        
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = new Date().toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
        });
        
        contentDiv.appendChild(bubbleDiv);
        contentDiv.appendChild(timeDiv);
        
        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        
        this.chatMessages.appendChild(messageDiv);
        
        // Render LaTeX formulas with MathJax if available
        if (window.MathJax && window.MathJax.typesetPromise) {
            window.MathJax.typesetPromise([bubbleDiv]).catch((err) => {
                console.warn('MathJax rendering error:', err);
            });
        }
        
        // Scroll to bottom
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        
        // Add to message history
        appState.messageHistory.push({
            sender,
            content,
            timestamp: Date.now(),
            isError
        });
    }

    createStreamingMessage() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        avatarDiv.innerHTML = '<i class="fas fa-robot"></i>';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const bubbleDiv = document.createElement('div');
        bubbleDiv.className = 'message-bubble streaming';
        bubbleDiv.innerHTML = '<span class="typing-indicator">...</span>';
        
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = new Date().toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
        });
        
        contentDiv.appendChild(bubbleDiv);
        contentDiv.appendChild(timeDiv);
        
        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        
        this.chatMessages.appendChild(messageDiv);
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        
        return messageDiv;
    }

    updateStreamingMessage(messageDiv, content) {
        const bubbleDiv = messageDiv.querySelector('.message-bubble');
        bubbleDiv.innerHTML = this.formatMessageContent(content) + '<span class="cursor">|</span>';
        bubbleDiv.classList.add('streaming');
        
        // Force immediate DOM update and scroll
        requestAnimationFrame(() => {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        });
        
        // Render LaTeX formulas with MathJax if available
        if (window.MathJax && window.MathJax.typesetPromise) {
            window.MathJax.typesetPromise([bubbleDiv]).catch((err) => {
                console.warn('MathJax rendering error:', err);
            });
        }
    }

    finalizeStreamingMessage(messageDiv, content, isError = false) {
        const bubbleDiv = messageDiv.querySelector('.message-bubble');
        bubbleDiv.classList.remove('streaming');
        
        if (isError) {
            bubbleDiv.style.color = '#ff4757';
            bubbleDiv.style.borderColor = '#ff4757';
        }
        
        bubbleDiv.innerHTML = this.formatMessageContent(content);
        
        // Render LaTeX formulas with MathJax if available
        if (window.MathJax && window.MathJax.typesetPromise) {
            window.MathJax.typesetPromise([bubbleDiv]).catch((err) => {
                console.warn('MathJax rendering error:', err);
            });
        }
        
        // Add to message history
        appState.messageHistory.push({
            sender: 'assistant',
            content,
            timestamp: Date.now(),
            isError
        });
        
        // Scroll to bottom
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    formatMessageContent(content) {
        // Basic text formatting with LaTeX support
        // Preserve LaTeX delimiters and format other content
        return content
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>');
        // Note: LaTeX formulas ($...$ and $$...$$) are preserved as-is for MathJax processing
    }

    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        
        // Style the notification
        Object.assign(notification.style, {
            position: 'fixed',
            top: '20px',
            right: '20px',
            padding: '12px 20px',
            borderRadius: '8px',
            color: 'white',
            fontWeight: '500',
            zIndex: '10000',
            animation: 'fadeInRight 0.3s ease',
            minWidth: '200px',
            maxWidth: '400px'
        });
        
        // Set background color based on type
        switch (type) {
            case 'success':
                notification.style.backgroundColor = '#00d26a';
                break;
            case 'error':
                notification.style.backgroundColor = '#ff4757';
                break;
            case 'warning':
                notification.style.backgroundColor = '#ffa502';
                break;
            default:
                notification.style.backgroundColor = '#0084ff';
        }
        
        document.body.appendChild(notification);
        
        // Remove after 3 seconds
        setTimeout(() => {
            notification.style.animation = 'fadeOutRight 0.3s ease';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }
}

// Notification animations
const notificationStyles = document.createElement('style');
notificationStyles.textContent = `
    @keyframes fadeInRight {
        from {
            opacity: 0;
            transform: translateX(100px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }
    
    @keyframes fadeOutRight {
        from {
            opacity: 1;
            transform: translateX(0);
        }
        to {
            opacity: 0;
            transform: translateX(100px);
        }
    }
`;
document.head.appendChild(notificationStyles);

// Initialize the application
let uiManager;

document.addEventListener('DOMContentLoaded', () => {
    // Initialize UI manager
    uiManager = new UIManager();
    
    // Update initial state
    appState.updateInputState();
    
    // Check initial connection if API key exists
    if (appState.apiKey) {
        setTimeout(() => {
            uiManager.handleTestConnection();
        }, 1000);
    }
    
    // Set initial status
    appState.updateConnectionStatus(false, appState.apiKey ? 'Checking...' : 'No API key');
    
    console.log('RAG Assistant initialized successfully');
});

// Handle window resize for responsive design
window.addEventListener('resize', () => {
    if (window.innerWidth <= 768 && appState.isSettingsOpen) {
        // On mobile, ensure settings panel is properly positioned
        document.body.style.overflow = 'hidden';
    }
});

// Export for debugging (if needed)
if (typeof window !== 'undefined') {
    window.appState = appState;
    window.apiService = apiService;
    window.uiManager = uiManager;
}