import asyncio
import logging
import threading
import time
from typing import Dict, Optional, Callable
from aiortc.contrib.media import MediaStreamTrack
import pyaudio
import numpy as np
import wave
import io

logger = logging.getLogger(__name__)

class LocalAudioPlayer:
    """
    A class to handle real-time audio playback of MediaStreamTracks on the local machine.
    This class manages audio streams from WebRTC connections and plays them locally.
    """
    
    def __init__(self):
        self.audio_tracks: Dict[str, MediaStreamTrack] = {}
        self.audio_streams: Dict[str, pyaudio.PyAudio.Stream] = {}
        self.is_playing: Dict[str, bool] = {}
        self.audio_threads: Dict[str, threading.Thread] = {}
        self.audio_format = pyaudio.paFloat32
        self.channels = 1
        self.rate = 48000  # Standard WebRTC sample rate
        self.chunk_size = 1024
        self.pyaudio_instance = None
        self.volume_controls: Dict[str, float] = {}
        self.audio_callbacks: Dict[str, Callable] = {}
        self.audio_available = False
        
        # Initialize PyAudio with better error handling
        self._initialize_audio()
    
    def _initialize_audio(self):
        """Initialize audio system with fallback options"""
        try:
            # Try to initialize PyAudio
            self.pyaudio_instance = pyaudio.PyAudio()
            
            # Test if we can actually open an audio stream
            try:
                # Try to get default output device info
                default_output = self.pyaudio_instance.get_default_output_device_info()
                logger.info(f"Default output device: {default_output['name']}")
                
                # Test opening a stream
                test_stream = self.pyaudio_instance.open(
                    format=self.audio_format,
                    channels=self.channels,
                    rate=self.rate,
                    output=True,
                    frames_per_buffer=self.chunk_size
                )
                test_stream.close()
                
                self.audio_available = True
                logger.info("PyAudio initialized successfully and audio output verified")
                
            except Exception as stream_error:
                logger.warning(f"Audio stream test failed: {stream_error}")
                # Try alternative audio formats
                self._try_alternative_audio_formats()
                
        except Exception as e:
            logger.error(f"Failed to initialize PyAudio: {e}")
            self._try_system_audio_fixes()
    
    def _try_alternative_audio_formats(self):
        """Try alternative audio formats if the default fails"""
        alternative_formats = [
            pyaudio.paInt16,
            pyaudio.paInt32,
            pyaudio.paInt24
        ]
        
        for alt_format in alternative_formats:
            try:
                test_stream = self.pyaudio_instance.open(
                    format=alt_format,
                    channels=self.channels,
                    rate=self.rate,
                    output=True,
                    frames_per_buffer=self.chunk_size
                )
                test_stream.close()
                
                self.audio_format = alt_format
                self.audio_available = True
                logger.info(f"Audio initialized with alternative format: {alt_format}")
                return
                
            except Exception as e:
                logger.debug(f"Alternative format {alt_format} failed: {e}")
                continue
        
        logger.error("All audio formats failed, audio playback will not be available")
        self.audio_available = False
    
    def _try_system_audio_fixes(self):
        """Try to fix common Linux audio system issues"""
        logger.info("Attempting to fix common Linux audio system issues...")
        
        # Check if we're running in a container or headless environment
        import os
        if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
            logger.warning("No display detected - running in headless mode")
            logger.info("Audio playback may not work in headless environments")
            self.audio_available = False
            return
        
        # Try to set environment variables that might help
        os.environ.setdefault('PULSE_LATENCY_MSEC', '30')
        os.environ.setdefault('ALSA_PCM_CARD', '0')
        os.environ.setdefault('ALSA_PCM_DEVICE', '0')
        
        logger.info("Set ALSA environment variables, trying PyAudio again...")
        
        try:
            self.pyaudio_instance = pyaudio.PyAudio()
            self.audio_available = True
            logger.info("PyAudio initialized after system fixes")
        except Exception as e:
            logger.error(f"PyAudio still failed after system fixes: {e}")
            self.audio_available = False
    
    def add_audio_track(self, peer_id: str, track: MediaStreamTrack, volume: float = 1.0) -> bool:
        """
        Add an audio track for local playback.
        
        Args:
            peer_id: Unique identifier for the peer
            track: MediaStreamTrack to play
            volume: Volume level (0.0 to 1.0)
            
        Returns:
            bool: True if track was added successfully
        """
        try:
            # Check if audio system is available
            if not self.audio_available:
                logger.warning(f"Cannot add audio track for peer {peer_id}: Audio system not available")
                return False
            
            if peer_id in self.audio_tracks:
                logger.warning(f"Audio track for peer {peer_id} already exists, replacing it")
                self.remove_audio_track(peer_id)
            
            self.audio_tracks[peer_id] = track
            self.volume_controls[peer_id] = max(0.0, min(1.0, volume))
            self.is_playing[peer_id] = False
            
            logger.info(f"Added audio track for peer {peer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add audio track for peer {peer_id}: {e}")
            return False
    
    def remove_audio_track(self, peer_id: str) -> bool:
        """
        Remove an audio track and stop its playback.
        
        Args:
            peer_id: Unique identifier for the peer
            
        Returns:
            bool: True if track was removed successfully
        """
        try:
            # Stop playback if active
            if peer_id in self.is_playing and self.is_playing[peer_id]:
                self.stop_audio(peer_id)
            
            # Clean up resources
            if peer_id in self.audio_tracks:
                del self.audio_tracks[peer_id]
            if peer_id in self.volume_controls:
                del self.volume_controls[peer_id]
            if peer_id in self.is_playing:
                del self.is_playing[peer_id]
            if peer_id in self.audio_callbacks:
                del self.audio_callbacks[peer_id]
            
            logger.info(f"Removed audio track for peer {peer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove audio track for peer {peer_id}: {e}")
            return False
    
    def start_audio(self, peer_id: str) -> bool:
        """
        Start playing audio from a specific peer's track.
        
        Args:
            peer_id: Unique identifier for the peer
            
        Returns:
            bool: True if audio started successfully
        """
        try:
            # Check if audio system is available
            if not self.audio_available:
                logger.warning(f"Cannot start audio for peer {peer_id}: Audio system not available")
                return False
            
            if peer_id not in self.audio_tracks:
                logger.error(f"No audio track found for peer {peer_id}")
                return False
            
            if self.is_playing.get(peer_id, False):
                logger.warning(f"Audio for peer {peer_id} is already playing")
                return True
            
            # Create and start audio thread
            audio_thread = threading.Thread(
                target=self._audio_playback_worker,
                args=(peer_id,),
                daemon=True
            )
            
            self.audio_threads[peer_id] = audio_thread
            self.is_playing[peer_id] = True
            audio_thread.start()
            
            logger.info(f"Started audio playback for peer {peer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start audio for peer {peer_id}: {e}")
            self.is_playing[peer_id] = False
            return False
    
    def stop_audio(self, peer_id: str) -> bool:
        """
        Stop playing audio from a specific peer's track.
        
        Args:
            peer_id: Unique identifier for the peer
            
        Returns:
            bool: True if audio stopped successfully
        """
        try:
            if peer_id not in self.is_playing or not self.is_playing[peer_id]:
                logger.warning(f"Audio for peer {peer_id} is not playing")
                return True
            
            # Stop the audio thread
            self.is_playing[peer_id] = False
            
            # Wait for thread to finish
            if peer_id in self.audio_threads:
                thread = self.audio_threads[peer_id]
                if thread.is_alive():
                    thread.join(timeout=1.0)
                del self.audio_threads[peer_id]
            
            logger.info(f"Stopped audio playback for peer {peer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop audio for peer {peer_id}: {e}")
            return False
    
    def set_volume(self, peer_id: str, volume: float) -> bool:
        """
        Set the volume for a specific peer's audio.
        
        Args:
            peer_id: Unique identifier for the peer
            volume: Volume level (0.0 to 1.0)
            
        Returns:
            bool: True if volume was set successfully
        """
        try:
            if peer_id not in self.volume_controls:
                logger.error(f"No audio track found for peer {peer_id}")
                return False
            
            self.volume_controls[peer_id] = max(0.0, min(1.0, volume))
            logger.info(f"Set volume for peer {peer_id} to {volume}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set volume for peer {peer_id}: {e}")
            return False
    
    def get_volume(self, peer_id: str) -> Optional[float]:
        """
        Get the current volume for a specific peer's audio.
        
        Args:
            peer_id: Unique identifier for the peer
            
        Returns:
            float: Current volume level, or None if peer not found
        """
        return self.volume_controls.get(peer_id)
    
    def add_audio_callback(self, peer_id: str, callback: Callable) -> bool:
        """
        Add a custom callback for audio processing.
        
        Args:
            peer_id: Unique identifier for the peer
            callback: Function to call with audio data
            
        Returns:
            bool: True if callback was added successfully
        """
        try:
            self.audio_callbacks[peer_id] = callback
            logger.info(f"Added audio callback for peer {peer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add audio callback for peer {peer_id}: {e}")
            return False
    
    def _audio_playback_worker(self, peer_id: str):
        """
        Worker thread for audio playback.
        
        Args:
            peer_id: Unique identifier for the peer
        """
        try:
            track = self.audio_tracks[peer_id]
            volume = self.volume_controls[peer_id]
            
            # Open audio stream
            stream = self.pyaudio_instance.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.rate,
                output=True,
                frames_per_buffer=self.chunk_size
            )
            
            self.audio_streams[peer_id] = stream
            
            logger.info(f"Audio stream opened for peer {peer_id}")
            
            # Create event loop for async operations
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Audio playback loop
                while self.is_playing.get(peer_id, False):
                    try:
                        # Read audio data from track using async
                        frame = loop.run_until_complete(track.recv())
                        
                        if frame is None:
                            break
                        
                        # Convert frame to numpy array
                        audio_data = np.frombuffer(frame.planes[0], dtype=np.float32)
                        
                        # Apply volume control
                        audio_data = audio_data * volume
                        
                        # Apply custom callback if available
                        if peer_id in self.audio_callbacks:
                            try:
                                audio_data = self.audio_callbacks[peer_id](audio_data)
                            except Exception as e:
                                logger.warning(f"Audio callback failed for peer {peer_id}: {e}")
                        
                        # Convert to bytes and play
                        audio_bytes = audio_data.astype(np.float32).tobytes()
                        stream.write(audio_bytes)
                        
                    except Exception as e:
                        logger.error(f"Error in audio playback loop for peer {peer_id}: {e}")
                        break
            finally:
                loop.close()
            
            # Clean up stream
            if peer_id in self.audio_streams:
                stream = self.audio_streams[peer_id]
                stream.stop_stream()
                stream.close()
                del self.audio_streams[peer_id]
            
            logger.info(f"Audio playback worker finished for peer {peer_id}")
            
        except Exception as e:
            logger.error(f"Fatal error in audio playback worker for peer {peer_id}: {e}")
            self.is_playing[peer_id] = False
    
    def get_audio_status(self, peer_id: str) -> Dict:
        """
        Get the current status of audio playback for a specific peer.
        
        Args:
            peer_id: Unique identifier for the peer
            
        Returns:
            Dict: Status information including playing state, volume, etc.
        """
        status = {
            "peer_id": peer_id,
            "has_track": peer_id in self.audio_tracks,
            "is_playing": self.is_playing.get(peer_id, False),
            "volume": self.volume_controls.get(peer_id, 0.0),
            "has_callback": peer_id in self.audio_callbacks
        }
        
        if peer_id in self.audio_streams:
            stream = self.audio_streams[peer_id]
            status["stream_active"] = stream.is_active()
            status["stream_stopped"] = stream.is_stopped()
        
        return status
    
    def get_audio_system_status(self) -> Dict:
        """
        Get the status of the audio system and available devices.
        
        Returns:
            Dict: Audio system status information
        """
        status = {
            "audio_available": self.audio_available,
            "pyaudio_initialized": self.pyaudio_instance is not None,
            "audio_format": str(self.audio_format),
            "sample_rate": self.rate,
            "channels": self.channels,
            "chunk_size": self.chunk_size
        }
        
        if self.pyaudio_instance:
            try:
                # Get device information
                device_count = self.pyaudio_instance.get_device_count()
                status["device_count"] = device_count
                
                # Get default output device
                try:
                    default_output = self.pyaudio_instance.get_default_output_device_info()
                    status["default_output_device"] = default_output['name']
                except Exception as e:
                    status["default_output_device"] = f"Error: {e}"
                
                # List available output devices
                output_devices = []
                for i in range(device_count):
                    try:
                        device_info = self.pyaudio_instance.get_device_info_by_index(i)
                        if device_info['maxOutputChannels'] > 0:
                            output_devices.append({
                                "index": i,
                                "name": device_info['name'],
                                "channels": device_info['maxOutputChannels'],
                                "sample_rate": device_info['defaultSampleRate']
                            })
                    except Exception as e:
                        continue
                
                status["output_devices"] = output_devices
                
            except Exception as e:
                status["device_info_error"] = str(e)
        
        return status
    
    def get_all_audio_status(self) -> Dict[str, Dict]:
        """
        Get the status of all audio tracks.
        
        Returns:
            Dict: Status information for all peers
        """
        return {peer_id: self.get_audio_status(peer_id) 
                for peer_id in self.audio_tracks.keys()}
    
    def pause_all_audio(self) -> bool:
        """
        Pause all active audio playback.
        
        Returns:
            bool: True if all audio was paused successfully
        """
        try:
            for peer_id in list(self.is_playing.keys()):
                if self.is_playing[peer_id]:
                    self.stop_audio(peer_id)
            
            logger.info("Paused all audio playback")
            return True
            
        except Exception as e:
            logger.error(f"Failed to pause all audio: {e}")
            return False
    
    def resume_all_audio(self) -> bool:
        """
        Resume all previously active audio playback.
        
        Returns:
            bool: True if all audio was resumed successfully
        """
        try:
            for peer_id in list(self.audio_tracks.keys()):
                if not self.is_playing.get(peer_id, False):
                    self.start_audio(peer_id)
            
            logger.info("Resumed all audio playback")
            return True
            
        except Exception as e:
            logger.error(f"Failed to resume all audio: {e}")
            return False
    
    def cleanup(self):
        """
        Clean up all resources and stop all audio playback.
        """
        try:
            logger.info("Cleaning up LocalAudioPlayer resources...")
            
            # Stop all audio
            for peer_id in list(self.is_playing.keys()):
                if self.is_playing[peer_id]:
                    self.stop_audio(peer_id)
            
            # Close PyAudio
            if self.pyaudio_instance:
                self.pyaudio_instance.terminate()
                self.pyaudio_instance = None
            
            # Clear all data structures
            self.audio_tracks.clear()
            self.audio_streams.clear()
            self.is_playing.clear()
            self.audio_threads.clear()
            self.volume_controls.clear()
            self.audio_callbacks.clear()
            
            logger.info("LocalAudioPlayer cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def retry_audio_initialization(self) -> bool:
        """
        Retry audio system initialization.
        
        Returns:
            bool: True if audio system was successfully initialized
        """
        logger.info("Retrying audio system initialization...")
        
        try:
            # Clean up existing audio instance
            if self.pyaudio_instance:
                self.pyaudio_instance.terminate()
                self.pyaudio_instance = None
            
            # Reset audio availability
            self.audio_available = False
            
            # Try to initialize again
            self._initialize_audio()
            
            if self.audio_available:
                logger.info("Audio system reinitialized successfully")
                return True
            else:
                logger.warning("Audio system reinitialization failed")
                return False
                
        except Exception as e:
            logger.error(f"Error during audio reinitialization: {e}")
            return False
    
    def __del__(self):
        """Destructor to ensure cleanup on deletion."""
        self.cleanup() 