# WebRTC Audio Streaming Frontend

This directory contains the complete frontend implementation for testing WebRTC audio streaming functionality.

## Files Overview

### 1. `index.html` - Main Test Suite Landing Page
- **Purpose**: Entry point for testing the audio streaming system
- **Features**: 
  - Navigation to the main audio streaming application
  - Setup instructions and prerequisites
  - Server configuration details
  - Testing scenarios and troubleshooting guide
  - Server status checker

### 2. `audio_streaming.html` - Main Audio Streaming Application
- **Purpose**: Full-featured WebRTC audio streaming interface
- **Features**:
  - Connection management (room/peer configuration)
  - Real-time audio capture and streaming
  - Audio visualization with animated bars
  - Recording capabilities
  - Audio statistics monitoring
  - Comprehensive logging system
  - Device selection and audio controls

### 3. `audio_streaming.js` - Core JavaScript Implementation
- **Purpose**: Handles all WebRTC functionality and user interactions
- **Features**:
  - WebRTC peer connection management
  - WebSocket signaling server communication
  - Audio stream processing and analysis
  - Real-time audio visualization
  - Recording and playback functionality
  - Error handling and connection recovery

## Getting Started

### Prerequisites
1. **Backend Server**: Ensure your Python WebRTC server is running
2. **Modern Browser**: Chrome, Firefox, Safari, or Edge with WebRTC support
3. **Microphone Access**: Browser permission for audio input
4. **Network Access**: Local network or internet access for WebRTC connections

### Quick Start
1. **Start the backend server**:
   ```bash
   cd /path/to/IECTranslate
   python run_server.py
   ```

2. **Open the test suite**:
   - Navigate to `front_end_test/index.html` in your browser
   - Click "🚀 Launch Audio Streaming App" to open the main application

3. **Configure connection**:
   - **Room ID**: Enter a room identifier (e.g., "test-room")
   - **Peer ID**: Enter a unique peer identifier (e.g., "peer-1")
   - **Server URL**: Use `ws://localhost:8000/ws` for local testing

4. **Connect and test**:
   - Click "Connect" to establish WebRTC connection
   - Click "Start Audio" to begin audio capture
   - Use "Start Recording" to record audio streams

## Features in Detail

### Connection Management
- **Room-based Architecture**: Multiple peers can join the same room
- **Unique Peer Identification**: Each peer has a unique ID for tracking
- **WebSocket Signaling**: Handles WebRTC offer/answer exchange
- **ICE Candidate Management**: Automatic NAT traversal and connection establishment

### Audio Streaming
- **Real-time Capture**: Live microphone input with configurable constraints
- **Device Selection**: Choose from available audio input devices
- **Audio Processing**: Echo cancellation, noise suppression, and auto-gain control
- **Quality Optimization**: Configurable audio parameters for different use cases

### Audio Visualization
- **Real-time Bars**: 32-band frequency analyzer with animated visualization
- **Audio Level Meter**: RMS-based audio level measurement in dB
- **Frequency Analysis**: FFT-based spectral analysis for real-time monitoring
- **Responsive Design**: Smooth animations with 60fps updates

### Recording System
- **WebM Format**: High-quality audio recording with Opus codec
- **Automatic Download**: Recordings are automatically saved to local storage
- **Timestamp Naming**: Unique filenames with timestamps
- **Chunk-based Recording**: Efficient memory usage for long recordings

### Statistics and Monitoring
- **Audio Level**: Real-time audio level in decibels
- **Sample Rate**: Current audio sample rate
- **Bitrate**: Estimated audio bitrate
- **Packet Loss**: Connection quality metrics
- **Connection State**: WebRTC connection status monitoring

### Logging and Debugging
- **Comprehensive Logging**: All connection events and errors are logged
- **Color-coded Messages**: Different log levels with visual indicators
- **Timestamp Information**: Precise timing for debugging
- **Console Integration**: Logs also appear in browser console

## Testing Scenarios

### 1. Single Peer Testing
- Connect with a single peer ID
- Test audio capture and playback
- Verify recording functionality
- Check audio visualization

### 2. Multi-Peer Testing
- Open multiple browser tabs
- Use different peer IDs for each tab
- Join the same room
- Test audio streaming between peers

### 3. Device Testing
- Test different microphone devices
- Verify audio quality across devices
- Test device switching during active sessions

### 4. Connection Testing
- Test connection establishment
- Verify reconnection after disconnection
- Test network interruption handling
- Check ICE connection states

### 5. Recording Testing
- Test audio recording start/stop
- Verify recording quality
- Test recording during active streaming
- Check file download functionality

## Configuration Options

### Audio Constraints
```javascript
const constraints = {
    audio: {
        deviceId: 'selected-device-id',
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: 44100,
        channelCount: 1
    }
};
```

### WebRTC Configuration
```javascript
const configuration = {
    iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' }
    ],
    iceCandidatePoolSize: 10
};
```

### Visualization Settings
```javascript
const analyser = audioContext.createAnalyser();
analyser.fftSize = 256;        // Frequency resolution
analyser.smoothingTimeConstant = 0.8;  // Smoothing factor
analyser.minDecibels = -90;    // Minimum dB level
analyser.maxDecibels = -10;    // Maximum dB level
```

## Troubleshooting

### Common Issues

#### Connection Problems
- **WebSocket Connection Failed**: Check server URL and server status
- **ICE Connection Failed**: Check firewall settings and STUN server accessibility
- **Peer Connection Timeout**: Verify network connectivity and server responsiveness

#### Audio Issues
- **No Audio Input**: Check microphone permissions and device selection
- **Poor Audio Quality**: Adjust audio constraints and check network conditions
- **Audio Delay**: Check for network latency and processing overhead

#### Recording Issues
- **Recording Not Starting**: Ensure audio stream is active and MediaRecorder is supported
- **File Not Downloading**: Check browser download settings and storage permissions
- **Poor Recording Quality**: Verify audio source quality and encoding settings

### Debug Steps
1. **Check Browser Console**: Look for JavaScript errors and WebRTC logs
2. **Verify Server Status**: Use the status checker in the test suite
3. **Check Network Tab**: Monitor WebSocket and WebRTC connections
4. **Test with Different Browsers**: Verify cross-browser compatibility
5. **Check Audio Permissions**: Ensure microphone access is granted

## Browser Compatibility

### Supported Browsers
- **Chrome 66+**: Full WebRTC support with all features
- **Firefox 60+**: Full WebRTC support with all features
- **Safari 11+**: WebRTC support with some limitations
- **Edge 79+**: Full WebRTC support with all features

### Feature Support Matrix
| Feature | Chrome | Firefox | Safari | Edge |
|---------|--------|---------|--------|------|
| WebRTC | ✅ | ✅ | ✅ | ✅ |
| MediaRecorder | ✅ | ✅ | ✅ | ✅ |
| AudioContext | ✅ | ✅ | ✅ | ✅ |
| getUserMedia | ✅ | ✅ | ✅ | ✅ |

## Performance Considerations

### Audio Processing
- **FFT Size**: 256 provides good balance between performance and resolution
- **Update Rate**: 60fps visualization for smooth user experience
- **Memory Usage**: Efficient audio buffer management for long sessions

### Network Optimization
- **ICE Candidate Pooling**: Reduces connection establishment time
- **STUN Server Fallback**: Multiple STUN servers for reliability
- **Connection Monitoring**: Automatic reconnection and error recovery

### Browser Optimization
- **RequestAnimationFrame**: Smooth visualization updates
- **Audio Worklet**: Future implementation for better audio processing
- **WebAssembly**: Potential for high-performance audio algorithms

## Security Considerations

### Local Development
- HTTP is acceptable for localhost testing
- WebRTC works without HTTPS in local environments
- Microphone access requires user permission

### Production Deployment
- HTTPS is required for WebRTC in production
- Secure WebSocket connections (WSS) recommended
- Implement proper authentication and authorization
- Consider rate limiting and connection quotas

## Future Enhancements

### Planned Features
- **Audio Effects**: Real-time audio filters and effects
- **Multi-room Support**: Advanced room management and switching
- **Screen Sharing**: Audio from screen capture
- **File Streaming**: Audio file streaming capabilities

### Technical Improvements
- **WebRTC Data Channels**: Metadata and control information
- **Audio Worklets**: High-performance audio processing
- **WebAssembly**: Native-speed audio algorithms
- **Service Workers**: Offline and background processing

## Support and Development

### Getting Help
- Check browser console for detailed error messages
- Review WebRTC connection states and ICE candidates
- Verify server logs for backend issues
- Test with different browsers and devices

### Contributing
- Report issues with detailed reproduction steps
- Include browser version and operating system
- Provide network configuration details
- Share relevant console logs and error messages

---

**Note**: This frontend implementation is designed for testing and development purposes. For production use, implement proper security measures, error handling, and user authentication. 