import asyncio
import sounddevice as sd
import numpy as np
from aiortc import MediaStreamTrack
import logging
from typing import Optional
import threading
import queue

logger = logging.getLogger(__name__)

class AudioPlayer:
    def __init__(self, track: MediaStreamTrack, device_id: Optional[int] = None):
        self.track = track
        self.device_id = device_id
        self.is_playing = False
        self.audio_queue = queue.Queue(maxsize=100)  # Buffer for audio frames
        self.sample_rate = 48000  # Default sample rate
        self.channels = 1  # Default mono
        
        # Auto-detect audio device if not specified
        if self.device_id is None:
            self.device_id = self._get_default_output_device()
        
        # Validate device
        if not self._validate_device():
            logger.warning(f"Invalid audio device {self.device_id}, using default")
            self.device_id = self._get_default_output_device()
    
    async def start(self):
        """Start playing audio from the track"""
        try:
            logger.info("Starting audio player...")
            self.is_playing = True
            
            # Start audio playback in a separate thread
            playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
            playback_thread.start()
            
            # Start receiving frames from the track
            await self._receive_frames()
            
        except Exception as e:
            logger.error(f"Error in audio player: {e}")
            self.is_playing = False
            raise
    
    async def _receive_frames(self):
        """Receive audio frames from the track and put them in the queue"""
        try:
            while self.is_playing:
                try:
                    # Receive frame with timeout to allow graceful shutdown
                    frame = await asyncio.wait_for(self.track.recv(), timeout=1.0)
                    
                    # Update sample rate and channels from first frame
                    if frame.sample_rate:
                        self.sample_rate = frame.sample_rate
                        logger.info(f"Audio sample rate: {self.sample_rate} Hz")
                    
                    # Detect channels from frame
                    samples = frame.to_ndarray()
                    if len(samples.shape) > 1:
                        detected_channels = samples.shape[1]
                    else:
                        detected_channels = 1
                    
                    if detected_channels != self.channels:
                        logger.info(f"Detected {detected_channels} channels, updating from {self.channels}")
                        self.channels = detected_channels
                    
                    # Handle different audio formats
                    if samples.dtype != np.float32:
                        # Convert to float32 and normalize to [-1, 1] range
                        if samples.dtype == np.int16:
                            samples = samples.astype(np.float32) / 32768.0
                        elif samples.dtype == np.int32:
                            samples = samples.astype(np.float32) / 2147483648.0
                        else:
                            samples = samples.astype(np.float32)
                    
                    # Ensure samples are 2D (samples, channels)
                    if len(samples.shape) == 1:
                        samples = samples.reshape(-1, 1)
                    
                    # Put in queue (non-blocking)
                    try:
                        self.audio_queue.put_nowait(samples)
                    except queue.Full:
                        # Queue is full, drop oldest frame
                        try:
                            self.audio_queue.get_nowait()
                            self.audio_queue.put_nowait(samples)
                        except queue.Empty:
                            pass
                            
                except asyncio.TimeoutError:
                    # No frame received within timeout, continue
                    continue
                except Exception as e:
                    logger.error(f"Error receiving frame: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Error in frame receiver: {e}")
        finally:
            self.is_playing = False
    
    def _playback_worker(self):
        """Worker thread for audio playback"""
        try:
            logger.info(f"Audio playback worker started - Sample rate: {self.sample_rate}, Channels: {self.channels}")
            
            # Configure sounddevice
            sd.default.samplerate = self.sample_rate
            sd.default.channels = self.channels
            sd.default.device = self.device_id
            
            # Create output stream
            with sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.float32,
                device=self.device_id,
                blocksize=1024,  # Adjust based on your needs
                latency='low'
            ) as stream:
                
                while self.is_playing:
                    try:
                        # Get audio frame from queue
                        samples = self.audio_queue.get(timeout=0.1)
                        
                        # Handle channel conversion if needed
                        samples = self._ensure_correct_channels(samples, self.channels)
                        
                        # Play the audio
                        stream.write(samples)
                        
                    except queue.Empty:
                        # No audio data, continue
                        continue
                    except Exception as e:
                        logger.error(f"Error in playback: {e}")
                        break
                        
        except Exception as e:
            logger.error(f"Error in playback worker: {e}")
        finally:
            logger.info("Audio playback worker stopped")
    
    def _ensure_correct_channels(self, samples: np.ndarray, target_channels: int) -> np.ndarray:
        """Ensure the audio samples have the correct number of channels"""
        try:
            current_channels = samples.shape[1] if len(samples.shape) > 1 else 1
            
            if current_channels == target_channels:
                return samples
            
            logger.info(f"Converting audio from {current_channels} to {target_channels} channels")
            
            if current_channels == 1 and target_channels == 2:
                # Mono to stereo: duplicate the mono channel
                return np.column_stack([samples, samples])
            elif current_channels == 2 and target_channels == 1:
                # Stereo to mono: average the channels
                return np.mean(samples, axis=1, keepdims=True)
            elif current_channels > target_channels:
                # More channels to fewer: take first N channels
                return samples[:, :target_channels]
            elif current_channels < target_channels:
                # Fewer channels to more: pad with zeros
                padded = np.zeros((samples.shape[0], target_channels), dtype=samples.dtype)
                padded[:, :current_channels] = samples
                return padded
            else:
                # Fallback: return as-is
                return samples
                
        except Exception as e:
            logger.error(f"Error in channel conversion: {e}")
            # Return original samples if conversion fails
            return samples
    
    def stop(self):
        """Stop audio playback"""
        logger.info("Stopping audio player...")
        self.is_playing = False
    
    def get_audio_devices(self):
        """Get list of available audio output devices"""
        try:
            devices = sd.query_devices()
            output_devices = []
            
            for i, device in enumerate(devices):
                if device['max_outputs'] > 0:
                    output_devices.append({
                        'id': i,
                        'name': device['name'],
                        'channels': device['max_outputs'],
                        'sample_rate': device['default_samplerate']
                    })
            
            return output_devices
        except Exception as e:
            logger.error(f"Error querying audio devices: {e}")
            return []
    
    def set_device(self, device_id: int):
        """Set audio output device"""
        try:
            devices = sd.query_devices()
            if 0 <= device_id < len(devices):
                device = devices[device_id]
                if device['max_outputs'] > 0:
                    self.device_id = device_id
                    logger.info(f"Audio device set to: {device['name']}")
                    return True
                else:
                    logger.error(f"Device {device_id} is not an output device")
                    return False
            else:
                logger.error(f"Invalid device ID: {device_id}")
                return False
        except Exception as e:
            logger.error(f"Error setting audio device: {e}")
            return False

    def _get_default_output_device(self) -> int:
        """Get the default audio output device ID"""
        try:
            devices = sd.query_devices()
            for i, device in enumerate(devices):
                if device['max_outputs'] > 0:
                    logger.info(f"Using default audio device: {device['name']} (ID: {i})")
                    return i
            return 0  # Fallback to first device
        except Exception as e:
            logger.error(f"Error detecting default audio device: {e}")
            return 0
    
    def _validate_device(self) -> bool:
        """Validate that the selected audio device is valid"""
        try:
            devices = sd.query_devices()
            if 0 <= self.device_id < len(devices):
                device = devices[self.device_id]
                if device['max_outputs'] > 0:
                    logger.info(f"Audio device validated: {device['name']}")
                    return True
                else:
                    logger.error(f"Device {self.device_id} is not an output device")
                    return False
            else:
                logger.error(f"Invalid device ID: {self.device_id}")
                return False
        except Exception as e:
            logger.error(f"Error validating audio device: {e}")
            return False

# Example usage function
async def play_audio_track(track: MediaStreamTrack, device_id: Optional[int] = None):
    """Helper function to play an audio track"""
    player = AudioPlayer(track, device_id)
    
    try:
        # List available devices
        devices = player.get_audio_devices()
        logger.info("Available audio output devices:")
        for device in devices:
            logger.info(f"  {device['id']}: {device['name']} ({device['channels']} channels, {device['sample_rate']} Hz)")
        
        # Start playback
        await player.start()
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error playing audio: {e}")
    finally:
        player.stop()
        logger.info("Audio playback stopped") 