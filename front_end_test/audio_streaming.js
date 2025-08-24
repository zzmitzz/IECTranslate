/**
 * WebRTC Audio Streaming JavaScript Implementation
 * Handles real-time audio streaming with WebRTC technology
 */

class AudioStreamingApp {
    constructor() {
        this.peerConnection = null;
        this.localStream = null;
        this.remoteStream = null;
        this.websocket = null;
        this.audioContext = null;
        this.analyser = null;
        this.mediaRecorder = null;
        this.recordingChunks = [];
        this.isRecording = false;
        this.isConnected = false;
        this.isAudioActive = false;
        this.roomId = '';
        this.peerId = '';
        this.serverUrl = '';
        this.apiKey = '';
        
        this.initializeElements();
        this.setupEventListeners();
        this.initializeAudioVisualizer();
        this.loadAudioDevices();
    }

    initializeElements() {
        // Connection elements
        this.roomIdInput = document.getElementById('roomId');
        this.peerIdInput = document.getElementById('peerId');
        this.serverUrlInput = document.getElementById('serverUrl');
        this.apiKeyInput = document.getElementById('apiKey');
        this.connectBtn = document.getElementById('connectBtn');
        this.disconnectBtn = document.getElementById('disconnectBtn');
        this.connectionStatus = document.getElementById('connectionStatus');
        this.connectionText = document.getElementById('connectionText');

        // Audio control elements
        this.startAudioBtn = document.getElementById('startAudioBtn');
        this.stopAudioBtn = document.getElementById('stopAudioBtn');
        this.startRecordingBtn = document.getElementById('startRecordingBtn');
        this.stopRecordingBtn = document.getElementById('stopRecordingBtn');
        this.recordingStatus = document.getElementById('recordingStatus');
        this.audioDeviceSelect = document.getElementById('audioDevice');

        // Statistics elements
        this.audioLevelElement = document.getElementById('audioLevel');
        this.sampleRateElement = document.getElementById('sampleRate');
        this.bitrateElement = document.getElementById('bitrate');
        this.packetLossElement = document.getElementById('packetLoss');

        // Audio visualizer
        this.audioBars = document.getElementById('audioBars');

        // Log elements
        this.logContainer = document.getElementById('logContainer');
        this.clearLogsBtn = document.getElementById('clearLogsBtn');
    }

    setupEventListeners() {
        this.connectBtn.addEventListener('click', () => this.connect());
        this.disconnectBtn.addEventListener('click', () => this.disconnect());
        this.startAudioBtn.addEventListener('click', () => this.startAudio());
        this.stopAudioBtn.addEventListener('click', () => this.stopAudio());
        this.startRecordingBtn.addEventListener('click', () => this.startRecording());
        this.stopRecordingBtn.addEventListener('click', () => this.stopRecording());
        this.clearLogsBtn.addEventListener('click', () => this.clearLogs());
        
        // Handle form submission
        document.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                if (e.target.id === 'roomId' || e.target.id === 'peerId' || e.target.id === 'serverUrl' || e.target.id === 'apiKey') {
                    this.connect();
                }
            }
        });
    }

    async loadAudioDevices() {
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            const audioInputs = devices.filter(device => device.kind === 'audioinput');
            
            this.audioDeviceSelect.innerHTML = '<option value="">Default</option>';
            audioInputs.forEach(device => {
                const option = document.createElement('option');
                option.value = device.deviceId;
                option.textContent = device.label || `Microphone ${device.deviceId.slice(0, 8)}`;
                this.audioDeviceSelect.appendChild(option);
            });
        } catch (error) {
            this.log('Error loading audio devices: ' + error.message, 'error');
        }
    }

    validateApiKey(apiKey) {
        // Basic validation - API key should not be empty and should have reasonable length
        if (!apiKey || apiKey.length < 8) {
            return false;
        }
        return true;
    }

    async connect() {
        this.roomId = this.roomIdInput.value.trim();
        this.peerId = this.peerIdInput.value.trim();
        this.serverUrl = this.serverUrlInput.value.trim();
        this.apiKey = this.apiKeyInput.value.trim();

        if (!this.roomId || !this.peerId || !this.serverUrl || !this.apiKey) {
            this.log('Please fill in all connection fields including API key', 'warning');
            return;
        }

        if (!this.validateApiKey(this.apiKey)) {
            this.log('API key format is invalid. Please check your API key.', 'error');
            return;
        }

        try {
            this.log('Connecting to WebRTC server...', 'info');
            this.updateConnectionStatus('connecting');
            
            // Initialize WebRTC peer connection
            await this.initializeWebRTC();
            
            // Connect to signaling server via WebSocket
            await this.connectWebSocket();
            
            this.isConnected = true;
            this.updateConnectionStatus('connected');
            this.updateButtonStates();
            this.log('Successfully connected to WebRTC server', 'success');
            
        } catch (error) {
            this.log('Connection failed: ' + error.message, 'error');
            this.updateConnectionStatus('disconnected');
        }
    }

    async initializeWebRTC() {
        try {
            // Create RTCPeerConnection with STUN servers
            const configuration = {
                iceServers: [
                    { urls: 'stun:stun.l.google.com:19302' },
                    { urls: 'stun:stun1.l.google.com:19302' }
                ]
            };

            this.peerConnection = new RTCPeerConnection(configuration);
            
            // Set up event handlers
            this.peerConnection.onicecandidate = (event) => {
                if (event.candidate) {
                    this.log(`Generated ICE candidate: ${event.candidate.candidate}`, 'info');
                    this.sendWebSocketMessage({
                        type: 'ice-candidate',
                        candidate: event.candidate,
                        roomId: this.roomId,
                        peerId: this.peerConnection.localDescription?.sdp ? this.peerId : 'unknown'
                    });
                } else {
                    this.log('ICE candidate generation completed', 'info');
                }
            };

            this.peerConnection.ontrack = (event) => {
                this.log('Received remote audio track', 'info');
                this.remoteStream = event.streams[0];
                this.setupRemoteAudio();
            };

            this.peerConnection.oniceconnectionstatechange = () => {
                this.log(`ICE connection state: ${this.peerConnection.iceConnectionState}`, 'info');
            };

            this.peerConnection.onconnectionstatechange = () => {
                this.log(`Connection state: ${this.peerConnection.connectionState}`, 'info');
            };

            this.log('WebRTC peer connection initialized', 'success');
            
        } catch (error) {
            throw new Error('Failed to initialize WebRTC: ' + error.message);
        }
    }

    async connectWebSocket() {
        return new Promise((resolve, reject) => {
            try {
                // Construct WebSocket URL with API key as query parameter
                const wsUrl = `${this.serverUrl}?api_key=${encodeURIComponent(this.apiKey)}`;
                this.websocket = new WebSocket(wsUrl);
                
                this.websocket.onopen = () => {
                    this.log('WebSocket connection established', 'success');
                    this.sendWebSocketMessage({
                        type: 'join-room',
                        roomId: this.roomId,
                        peerId: this.peerId
                    });
                    resolve();
                };

                this.websocket.onmessage = (event) => {
                    this.handleWebSocketMessage(JSON.parse(event.data));
                };

                this.websocket.onerror = (error) => {
                    this.log('WebSocket error: ' + error.message, 'error');
                    reject(error);
                };

                this.websocket.onclose = () => {
                    this.log('WebSocket connection closed', 'warning');
                    this.handleDisconnection();
                };

            } catch (error) {
                reject(new Error('Failed to create WebSocket: ' + error.message));
            }
        });
    }

    handleWebSocketMessage(message) {
        // Log all incoming messages for debugging
        this.log(`Received message type: ${message.type}`, 'info');
        console.log('Full message received:', message);
        
        switch (message.type) {
            case 'offer':
                this.handleOffer(message);
                break;
            case 'answer':
                this.handleAnswer(message);
                break;
            case 'ice-candidate':
                this.handleIceCandidate(message);
                break;
            case 'room-joined':
                this.log('Successfully joined room: ' + message.roomId, 'success');
                break;
            case 'user-joined-room':
                this.log('User joined room: ' + message.peerId, 'info');
                // If we have an active audio stream, create an offer for the new user
                if (this.isAudioActive && this.localStream) {
                    this.createAndSendOffer();
                }
                break;
            case 'user-left-room':
                this.log('User left room: ' + message.peerId, 'info');
                break;
            case 'auth-error':
                this.log('Authentication failed: ' + message.message, 'error');
                this.handleDisconnection();
                break;
            case 'error':
                this.log('Server error: ' + message.message, 'error');
                break;
            default:
                this.log('Unknown message type: ' + message.type, 'warning');
        }
    }

    async handleOffer(message) {
        try {
            this.log('Received offer, setting remote description...', 'info');
            
            // Set the remote description from the offer
            await this.peerConnection.setRemoteDescription(new RTCSessionDescription(message.offer));
            
            // Create and send answer
            const answer = await this.peerConnection.createAnswer();
            await this.peerConnection.setLocalDescription(answer);
            
            // Send answer back to the signaling server
            this.sendWebSocketMessage({
                type: 'answer',
                answer: answer,
                roomId: this.roomId,
                peerId: this.peerId
            });
            
            this.log('Answer sent successfully', 'success');
            
        } catch (error) {
            this.log('Error handling offer: ' + error.message, 'error');
        }
    }

    async handleAnswer(message) {
        try {
            this.log('Received answer, setting remote description...', 'info');
            
            // Extract the answer data
            const answer = message.answer;
            
            // Set the remote description from the answer
            await this.peerConnection.setRemoteDescription(new RTCSessionDescription({
                type: answer.type,
                sdp: answer.sdp
            }));
            
            this.log('Remote description set successfully', 'success');
            
            // NOW add the audio track to trigger the onTrack event on the server
            if (this.localStream && this.isAudioActive) {
                this.log('Adding audio track to peer connection...', 'info');
                this.log(`Peer connection state: ${this.peerConnection.connectionState}`, 'info');
                this.log(`ICE connection state: ${this.peerConnection.iceConnectionState}`, 'info');
                this.log(`Signaling state: ${this.peerConnection.signalingState}`, 'info');
                
                // Check if connection is ready for adding tracks
                if (this.peerConnection.connectionState === 'connected' || 
                    this.peerConnection.iceConnectionState === 'connected' ||
                    this.peerConnection.signalingState === 'stable') {
                    
                    this.localStream.getTracks().forEach(track => {
                        this.log(`Adding track: ${track.kind}, ID: ${track.id}`, 'info');
                        const sender = this.peerConnection.addTrack(track, this.localStream);
                        this.log(`Track added, sender: ${sender ? 'created' : 'failed'}`, 'info');
                    });
                    this.log('Audio track added to peer connection', 'success');
                } else {
                    this.log('Connection not ready, waiting for stable state...', 'info');
                    // Wait for connection to become stable
                    this.peerConnection.onconnectionstatechange = () => {
                        if (this.peerConnection.connectionState === 'connected') {
                            this.log('Connection stable, now adding audio track...', 'info');
                            this.localStream.getTracks().forEach(track => {
                                this.log(`Adding track: ${track.kind}, ID: ${track.id}`, 'info');
                                const sender = this.peerConnection.addTrack(track, this.localStream);
                                this.log(`Track added, sender: ${sender ? 'created' : 'failed'}`, 'info');
                            });
                            this.log('Audio track added to peer connection after connection stabilization', 'success');
                        }
                    };
                }
            }
            
            // Handle ICE candidates if they were included in the answer
            if (answer.ice_candidates && Array.isArray(answer.ice_candidates)) {
                this.log(`Processing ${answer.ice_candidates.length} ICE candidates...`, 'info');
                
                for (const candidateData of answer.ice_candidates) {
                    try {
                        const iceCandidate = new RTCIceCandidate({
                            candidate: candidateData.candidate,
                            sdpMid: candidateData.sdpMid,
                            sdpMLineIndex: candidateData.sdpMLineIndex
                        });
                        
                        await this.peerConnection.addIceCandidate(iceCandidate);
                        this.log('ICE candidate added successfully', 'info');
                    } catch (error) {
                        this.log('Error adding ICE candidate: ' + error.message, 'warning');
                    }
                }
                
                this.log('All ICE candidates processed', 'success');
            } else {
                this.log('No ICE candidates included in answer', 'info');
            }
            
        } catch (error) {
            this.log('Error handling answer: ' + error.message, 'error');
        }
    }

    async handleIceCandidate(message) {
        try {
            this.log(`Received ICE candidate: ${message.candidate?.candidate || 'unknown'}`, 'info');
            
            if (this.peerConnection && this.peerConnection.remoteDescription) {
                const iceCandidate = new RTCIceCandidate(message.candidate);
                await this.peerConnection.addIceCandidate(iceCandidate);
                this.log('ICE candidate added successfully', 'success');
                
                // Log the current WebRTC state after adding candidate
                this.logWebRTCState();
            } else {
                this.log('Cannot add ICE candidate: peer connection not ready or no remote description', 'warning');
            }
        } catch (error) {
            this.log('Error adding ICE candidate: ' + error.message, 'error');
            console.error('ICE candidate error details:', error);
        }
    }

    async startAudio() {
        try {
            this.log('Starting audio capture...', 'info');
            
            const constraints = {
                audio: {
                    deviceId: this.audioDeviceSelect.value || undefined,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                },
                video: false
            };

            this.localStream = await navigator.mediaDevices.getUserMedia(constraints);
            
            // Set up audio analysis
            this.setupAudioAnalysis();
            
            // Create and send offer to establish WebRTC connection
            // The track will be added after the answer is received
            await this.createAndSendOffer();
            
            this.isAudioActive = true;
            this.updateButtonStates();
            this.log('Audio capture started successfully', 'success');
            
        } catch (error) {
            this.log('Failed to start audio: ' + error.message, 'error');
        }
    }

    async createAndSendOffer() {
        try {
            this.log('Creating WebRTC offer...', 'info');
            
            // Create offer
            const offer = await this.peerConnection.createOffer();
            await this.peerConnection.setLocalDescription(offer);
            
            // Send offer to signaling server
            this.sendWebSocketMessage({
                type: 'offer',
                offer: offer,
                roomId: this.roomId,
                peerId: this.peerId
            });
            
            this.log('WebRTC offer sent successfully', 'success');
            
        } catch (error) {
            this.log('Failed to create and send offer: ' + error.message, 'error');
            throw error;
        }
    }

    stopAudio() {
        try {
            // Stop all local audio tracks
            if (this.localStream) {
                this.localStream.getTracks().forEach(track => {
                    track.stop();
                });
                this.localStream = null;
            }
            
            // Remove all senders from the peer connection
            if (this.peerConnection) {
                this.peerConnection.getSenders().forEach(sender => {
                    if (sender.track) {
                        this.peerConnection.removeTrack(sender);
                    }
                });
            }
            
            this.isAudioActive = false;
            this.updateButtonStates();
            this.log('Audio capture stopped and WebRTC tracks cleaned up', 'info');
            
        } catch (error) {
            this.log('Error stopping audio: ' + error.message, 'error');
        }
    }

    setupAudioAnalysis() {
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = this.audioContext.createMediaStreamSource(this.localStream);
            
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 256;
            source.connect(this.analyser);
            
            this.startAudioVisualization();
            
        } catch (error) {
            this.log('Failed to setup audio analysis: ' + error.message, 'error');
        }
    }

    startAudioVisualization() {
        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        
        const updateVisualization = () => {
            if (!this.analyser || !this.isAudioActive) return;
            
            this.analyser.getByteFrequencyData(dataArray);
            this.updateAudioBars(dataArray);
            this.updateAudioStatistics(dataArray);
            
            requestAnimationFrame(updateVisualization);
        };
        
        updateVisualization();
    }

    updateAudioBars(dataArray) {
        const barCount = 32;
        const bars = [];
        
        for (let i = 0; i < barCount; i++) {
            const index = Math.floor(i * dataArray.length / barCount);
            const value = dataArray[index] / 255;
            const height = Math.max(2, value * 180);
            
            bars.push(`<div class="audio-bar" style="height: ${height}px;"></div>`);
        }
        
        this.audioBars.innerHTML = bars.join('');
    }

    updateAudioStatistics(dataArray) {
        // Calculate audio level (RMS)
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
            sum += (dataArray[i] / 255) ** 2;
        }
        const rms = Math.sqrt(sum / dataArray.length);
        const db = 20 * Math.log10(rms);
        
        this.audioLevelElement.textContent = db.toFixed(1);
        this.sampleRateElement.textContent = this.audioContext?.sampleRate || 0;
        
        // Simulate other statistics (in a real implementation, these would come from WebRTC stats)
        this.bitrateElement.textContent = Math.floor(Math.random() * 128 + 64);
        this.packetLossElement.textContent = (Math.random() * 5).toFixed(2);
    }

    setupRemoteAudio() {
        if (this.remoteStream) {
            const audioElement = document.createElement('audio');
            audioElement.srcObject = this.remoteStream;
            audioElement.autoplay = true;
            audioElement.controls = true;
            audioElement.style.width = '100%';
            audioElement.style.marginTop = '20px';
            
            // Add remote audio element to the page
            const audioControls = document.querySelector('.audio-controls');
            const existingRemoteAudio = audioControls.querySelector('.remote-audio');
            if (existingRemoteAudio) {
                existingRemoteAudio.remove();
            }
            
            const remoteAudioContainer = document.createElement('div');
            remoteAudioContainer.className = 'remote-audio';
            remoteAudioContainer.innerHTML = '<h3>🔊 Remote Audio</h3>';
            remoteAudioContainer.appendChild(audioElement);
            audioControls.appendChild(remoteAudioContainer);
            
            this.log('Remote audio setup complete', 'success');
        }
    }

    async startRecording() {
        if (!this.localStream) {
            this.log('No audio stream available for recording', 'warning');
            return;
        }

        try {
            this.recordingChunks = [];
            this.mediaRecorder = new MediaRecorder(this.localStream, {
                mimeType: 'audio/webm;codecs=opus'
            });

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.recordingChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = () => {
                const blob = new Blob(this.recordingChunks, { type: 'audio/webm' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `audio_recording_${Date.now()}.webm`;
                a.click();
                URL.revokeObjectURL(url);
                this.log('Recording saved successfully', 'success');
            };

            this.mediaRecorder.start();
            this.isRecording = true;
            this.recordingStatus.classList.remove('hidden');
            this.updateButtonStates();
            this.log('Audio recording started', 'success');
            
        } catch (error) {
            this.log('Failed to start recording: ' + error.message, 'error');
        }
    }

    stopRecording() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;
            this.recordingStatus.classList.add('hidden');
            this.updateButtonStates();
            this.log('Audio recording stopped', 'info');
        }
    }

    disconnect() {
        this.log('Disconnecting...', 'info');
        
        // Stop recording if active
        if (this.isRecording) {
            this.stopRecording();
        }
        
        // Stop audio if active
        if (this.isAudioActive) {
            this.stopAudio();
        }
        
        // Close WebRTC connection
        if (this.peerConnection) {
            this.peerConnection.close();
            this.peerConnection = null;
        }
        
        // Close WebSocket connection
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }
        
        // Reset state
        this.isConnected = false;
        this.isAudioActive = false;
        this.isRecording = false;
        this.localStream = null;
        this.remoteStream = null;
        this.apiKey = '';
        
        this.updateConnectionStatus('disconnected');
        this.updateButtonStates();
        this.log('Disconnected successfully', 'info');
    }

    handleDisconnection() {
        this.isConnected = false;
        this.updateConnectionStatus('disconnected');
        this.updateButtonStates();
        this.log('Connection lost', 'warning');
    }

    updateConnectionStatus(status) {
        this.connectionStatus.className = 'status-indicator';
        
        switch (status) {
            case 'connected':
                this.connectionStatus.classList.add('status-connected');
                this.connectionText.textContent = 'Connected';
                break;
            case 'connecting':
                this.connectionStatus.classList.add('status-disconnected');
                this.connectionText.textContent = 'Connecting...';
                break;
            case 'disconnected':
                this.connectionStatus.classList.add('status-disconnected');
                this.connectionText.textContent = 'Disconnected';
                break;
        }
    }

    updateButtonStates() {
        this.connectBtn.disabled = this.isConnected;
        this.disconnectBtn.disabled = !this.isConnected;
        this.startAudioBtn.disabled = !this.isConnected || this.isAudioActive;
        this.stopAudioBtn.disabled = !this.isAudioActive;
        this.startRecordingBtn.disabled = !this.isAudioActive || this.isRecording;
        this.stopRecordingBtn.disabled = !this.isRecording;
    }

    sendWebSocketMessage(message) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify(message));
        } else {
            this.log('WebSocket not connected', 'error');
        }
    }

    log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry log-${type}`;
        logEntry.innerHTML = `<span class="timestamp">[${timestamp}]</span> ${message}`;
        
        this.logContainer.appendChild(logEntry);
        this.logContainer.scrollTop = this.logContainer.scrollHeight;
        
        // Also log to console for debugging
        console.log(`[${type.toUpperCase()}] ${message}`);
    }

    logWebRTCState() {
        if (this.peerConnection) {
            this.log(`WebRTC State - Connection: ${this.peerConnection.connectionState}, ICE: ${this.peerConnection.iceConnectionState}, Signaling: ${this.peerConnection.signalingState}`, 'info');
        }
    }

    clearLogs() {
        this.logContainer.innerHTML = '';
        this.log('Logs cleared', 'info');
    }

    initializeAudioVisualizer() {
        // Create initial audio bars
        const barCount = 32;
        const bars = [];
        
        for (let i = 0; i < barCount; i++) {
            bars.push('<div class="audio-bar" style="height: 2px;"></div>');
        }
        
        this.audioBars.innerHTML = bars.join('');
    }

    async reconnect() {
        try {
            this.log('Attempting to reconnect...', 'info');
            
            // Clean up existing connections
            if (this.websocket) {
                this.websocket.close();
            }
            
            if (this.peerConnection) {
                this.peerConnection.close();
            }
            
            // Reset connection state
            this.isConnected = false;
            this.updateConnectionStatus('disconnected');
            
            // Reinitialize WebRTC and WebSocket
            await this.initializeWebRTC();
            await this.connectWebSocket();
            
            // If audio was active, restart it
            if (this.isAudioActive) {
                await this.startAudio();
            }
            
            this.isConnected = true;
            this.updateConnectionStatus('connected');
            this.updateButtonStates();
            this.log('Reconnection successful', 'success');
            
        } catch (error) {
            this.log('Reconnection failed: ' + error.message, 'error');
            this.updateConnectionStatus('disconnected');
        }
    }
}

// Initialize the application when the page loads
document.addEventListener('DOMContentLoaded', () => {
    window.audioApp = new AudioStreamingApp();
    
    // Add some helpful tips
    console.log('WebRTC Audio Streaming App initialized!');
    console.log('Make sure your WebRTC server is running and accessible.');
    console.log('Check the browser console for detailed logs.');
}); 