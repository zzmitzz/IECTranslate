
import asyncio
import json
import logging
from threading import local
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaStreamTrack, MediaPlayer, MediaRecorder, MediaRelay
from typing import Dict, Set, Optional
from .room import Rooms
from .audio_handler import AudioStreamHandler, initialize_audio_processors
import sounddevice as sd
from av import AudioFrame
import numpy as np
from collections import deque
logger = logging.getLogger(__name__)

class WebRTCHandler : 
    def __init__(self):
        self.room = Rooms()
        self.connections: Dict[str, RTCPeerConnection] = {}
        self.audio_tracks: Dict[str, MediaStreamTrack] = {}
        self.audio_handler = AudioStreamHandler()
        self.media_relay = MediaRelay()  # For forwarding media between peers
        
        # Initialize default audio processors
        initialize_audio_processors(self.audio_handler)

    async def create_peer_connection(self, room_id: str, peer_id: str) -> RTCPeerConnection:
        
        config = RTCConfiguration([
            RTCIceServer(urls="stun:stun.l.google.com:19302"),
            RTCIceServer(urls="stun:stun1.l.google.com:19302"),
            RTCIceServer(urls="stun:stun2.l.google.com:19302"),
            RTCIceServer(urls="stun:stun3.l.google.com:19302"),
            RTCIceServer(urls="stun:stun4.l.google.com:19302"),
            RTCIceServer(urls="stun:stun.stunprotocol.org:3478"),
            RTCIceServer(urls="stun:stun1.opentelecom.ro:3478"),
        ])
        
        logger.info(f"Creating RTCPeerConnection with ICE configuration: {config}")
        
        pc = RTCPeerConnection(config)
        self.connections[peer_id] = pc

        # Set up audio track handling
        @pc.on("track")
        async def on_track(track):
            print(f"=== ONTRACK EVENT TRIGGERED ===")
            print(f"Received {track.kind} track from peer {peer_id}")
            print(f"Track ID: {track.id}, Track kind: {track.kind}")
            print(f"Peer connection state: {pc.connectionState}")
            print(f"ICE connection state: {pc.iceConnectionState}")
            
            if track.kind == "audio":
                try:
                    # Use media relay to create a relayed track that can be shared
                    relayed_track = self.media_relay.subscribe(track)
                    self.audio_tracks[peer_id] = relayed_track
                    
                    # Process the audio track with error handling
                    processed_track = await self.audio_handler.process_audio_track(peer_id, relayed_track)
                    
                    # Ensure we have a valid track before proceeding
                    if processed_track is not None:
                        # Handle incoming audio track
                        await self.handle_audio_track(peer_id, processed_track)
                    else:
                        logger.error(f"Audio processing failed for peer {peer_id}, using original track")
                        await self.handle_audio_track(peer_id, relayed_track)
                        
                except Exception as e:
                    logger.error(f"Error handling audio track from peer {peer_id}: {e}")
                    # Fallback to using the original track
                    try:
                        await self.handle_audio_track(peer_id, track)
                    except Exception as fallback_error:
                        logger.error(f"Fallback audio handling also failed for peer {peer_id}: {fallback_error}")
            else:
                print(f"Unsupported track type: {track.kind}")

        self.room.join(room_id, peer_id)
        return pc

    async def handle_audio_track(self, peer_id: str, track: MediaStreamTrack):
        """Handle incoming audio track from a peer"""
        logger.info(f"Setting up audio track handling for peer {peer_id}")
        
        # Update audio statistics
        self.audio_handler.update_audio_stats(peer_id, {
            "track_active": True,
            "track_type": "audio",
            "timestamp": asyncio.get_event_loop().time()
        })
        
        # Get room information for logging
        room_id = self.room.get_peer_room(peer_id)
        room_peers = self.room.get_peers_in_room(room_id) if room_id else set()
        other_peers_count = len([p for p in room_peers if p != peer_id])
        
        logger.info(f"Peer {peer_id} in room {room_id} with {other_peers_count} other peers")
        print(f"Peer {peer_id} in room {room_id} with {other_peers_count} other peers")
        # Create local audio player for testing
        local_player = AudioPlayerTrack(track)
        local_player.start()
        # logger.info(f"Created AudioPlayerTrack for peer {peer_id}")
        
        # # Forward the audio track to other peers in the same room
        # await self.forward_audio_track_to_room(peer_id, track)
        
        # logger.info(f"Audio track from peer {peer_id} is now active and processed")
        
        # # Log track details for debugging
        # logger.info(f"Track ID: {track.id}, Kind: {track.kind}, Enabled: {track.enabled}")
        
        # # Start audio processing in background (don't block the main function)
        # asyncio.create_task(self.process_audio_track(peer_id, local_player))



    async def forward_audio_track_to_room(self, source_peer_id: str, track: MediaStreamTrack):
        """Forward audio track to all other peers in the same room"""
        try:
            # Validate input parameters
            if not track or not hasattr(track, 'kind'):
                logger.error(f"Invalid track object for peer {source_peer_id}")
                return
            
            if track.kind != "audio":
                logger.warning(f"Track is not audio type: {track.kind}")
                return
            
            # Get the room ID for this peer
            room_id = self.room.get_peer_room(source_peer_id)
            if not room_id:
                logger.warning(f"Peer {source_peer_id} not in any room")
                return
            
            # Get all other peers in the same room (excluding the source peer)
            room_peers = self.room.get_peers_in_room(room_id)
            other_peers = [peer_id for peer_id in room_peers if peer_id != source_peer_id]
            
            if not other_peers:
                logger.info(f"No other peers in room {room_id} to forward audio to")
                return
            
            logger.info(f"Forwarding audio track from {source_peer_id} to {len(other_peers)} other peers in room {room_id}")
            
            # Forward audio track to all other peers using media relay
            successful_forwards = 0
            for peer_id in other_peers:
                if peer_id in self.connections:
                    try:
                        pc = self.connections[peer_id]
                        if pc.connectionState == "connected":
                            # Create a relayed track for this peer
                            relayed_track = self.media_relay.subscribe(track)
                            # Add the relayed track to the peer's connection
                            sender = pc.addTrack(relayed_track)
                            successful_forwards += 1
                            logger.info(f"Successfully forwarded audio track from {source_peer_id} to {peer_id}")
                        else:
                            logger.warning(f"Peer {peer_id} connection not ready (state: {pc.connectionState})")
                    except Exception as e:
                        logger.error(f"Failed to forward audio track to {peer_id}: {e}")
                else:
                    logger.warning(f"Peer {peer_id} not found in connections, skipping audio forwarding")
            
            logger.info(f"Audio forwarding completed: {successful_forwards}/{len(other_peers)} peers received the track")
                        
        except Exception as e:
            logger.error(f"Error forwarding audio track: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    async def add_audio_track(self, peer_id: str, audio_source: Optional[str] = None):
        """Add an audio track to the peer connection"""
        if peer_id not in self.connections:
            raise ValueError(f"No connection found for peer {peer_id}")
        
        pc = self.connections[peer_id]
        
        if audio_source:
            # Create a media player from an audio file or stream
            player = MediaPlayer(audio_source)
            audio_track = player.audio
        else:
            # Create a default audio track (you might want to implement a custom audio source)
            # For now, we'll just return None as this requires more complex implementation
            logger.warning("No audio source provided, cannot create audio track")
            return None
        
        if audio_track:
            sender = pc.addTrack(audio_track)
            logger.info(f"Added audio track to peer {peer_id}")
            return sender
        
        return None

    async def start_audio_recording(self, peer_id: str, filename: str) -> bool:
        """Start recording audio from a specific peer"""
        return await self.audio_handler.start_recording(peer_id, filename)
    
    async def stop_audio_recording(self, peer_id: str) -> bool:
        """Stop recording audio from a specific peer"""
        return await self.audio_handler.stop_recording(peer_id)
    
    def get_audio_statistics(self, peer_id: str) -> Dict:
        """Get audio statistics for a specific peer"""
        return self.audio_handler.get_audio_stats(peer_id)
    
    def get_all_audio_statistics(self) -> Dict[str, Dict]:
        """Get audio statistics for all peers"""
        return self.audio_handler.audio_stats

    async def handle_offer(self, room_id: str, peer_id: str, offer: dict):
        print("handle_offer", room_id, peer_id, offer)
        pc = await self.create_peer_connection(room_id, peer_id)
        
        # Set up ICE candidate collection BEFORE setting local description
        ice_candidates = []
        ice_gathering_started = asyncio.Event()
        ice_gathering_complete = asyncio.Event()
        
        @pc.on("icecandidate")
        def on_ice_candidate(candidate):
            ice_gathering_started.set()
            if candidate:
                logger.info(f"ICE candidate generated for peer {peer_id}: {candidate.candidate}")
                logger.info(f"ICE candidate details - sdpMid: {candidate.sdpMid}, sdpMLineIndex: {candidate.sdpMLineIndex}")
                ice_candidates.append({
                    "candidate": candidate.candidate,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex
                })
            else:
                logger.info(f"ICE candidate generation completed for peer {peer_id}")
                ice_gathering_complete.set()
        
        @pc.on("connectionstatechange")
        def on_connection_state_change():
            logger.info(f"Connection state changed for peer {peer_id}: {pc.connectionState}")
    
        @pc.on("iceconnectionstatechange") 
        def on_ice_connection_state_change():
            print(f"ICE connection state changed for peer {peer_id}: {pc.iceConnectionState}")
    
        # Also monitor ICE gathering state changes
        @pc.on("icegatheringstatechange")
        def on_ice_gathering_state_change():
            logger.info(f"ICE gathering state changed for peer {peer_id}: {pc.iceGatheringState}")
            if pc.iceGatheringState == "complete":
                logger.info(f"ICE gathering completed via state change for peer {peer_id}")
                ice_gathering_complete.set()
        
        await pc.setRemoteDescription(
            RTCSessionDescription(
                type=offer["type"],
                sdp=offer["sdp"],
            )
        )

        answer = await pc.createAnswer()
        print(f"Created answer for peer {peer_id}, SDP: {answer.sdp[:200]}...")
        
        # ICE gathering starts here when we set local description
        await pc.setLocalDescription(answer)
        print(f"Set local description for peer {peer_id}")
        
        print(f"Waiting for ICE gathering to complete for peer {peer_id}")
        print(f"Current ICE gathering state: {pc.iceGatheringState}")
        print(f"Current connection state: {pc.connectionState}")
        print(f"Current ICE connection state: {pc.iceConnectionState}")
        
        # Wait for ICE gathering to complete with timeout
        try:
            await asyncio.wait_for(ice_gathering_complete.wait(), timeout=15.0)  # 30 second timeout
            logger.info(f"ICE gathering completed for peer {peer_id}")
        except asyncio.TimeoutError:
            logger.warning(f"ICE gathering timeout for peer {peer_id}, proceeding with {len(ice_candidates)} candidates")
            logger.warning(f"ICE gathering state at timeout: {pc.iceGatheringState}")
        
        # Also check the gathering state
        logger.info(f"Final ICE gathering state: {pc.iceGatheringState}")
        logger.info(f"Total ICE candidates collected: {len(ice_candidates)}")
        
        # Log all collected candidates for debugging
        for i, candidate in enumerate(ice_candidates):
            logger.info(f"ICE Candidate {i+1}: {candidate}")

        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
            "ice_candidates": ice_candidates
        }
    
    async def handle_answer(self, user_id: str, answer: dict):
        """Handle WebRTC answer"""
        logger.info(f"=== HANDLE ANSWER CALLED ===")
        logger.info(f"User ID: {user_id}")
        logger.info(f"Answer: {answer}")
        
        if user_id not in self.connections:
            logger.error(f"No connection found for user {user_id}")
            raise ValueError(f"No connection found for user {user_id}")
        
        pc = self.connections[user_id]
        logger.info(f"Found peer connection for user {user_id}")
        logger.info(f"Connection state: {pc.connectionState}")
        logger.info(f"ICE connection state: {pc.iceConnectionState}")
        
        await pc.setRemoteDescription(RTCSessionDescription(
            sdp=answer["sdp"],
            type=answer["type"]
        ))
        
        logger.info(f"Remote description set successfully for user {user_id}")
        logger.info(f"Updated connection state: {pc.connectionState}")
        logger.info(f"Updated ICE connection state: {pc.iceConnectionState}")

    async def handle_candidate(self, room_id: str, peer_id: str, candidate: dict):
        print("handle_candidate", room_id, peer_id, candidate)
        if peer_id not in self.connections:
            raise ValueError(f"No connection found for user {peer_id}")
        
        pc = self.connections[peer_id]
        
        try:
            # Parse the ICE candidate string to extract required parameters
            candidate_str = candidate["candidate"]
            
            # Parse candidate string format: "candidate:1 1 UDP 2122252543 192.168.1.1 54321 typ host"
            # Format: foundation priority protocol priority2 ip port typ type [relatedAddress] [relatedPort] [tcpType]
            parts = candidate_str.split()
            
            if len(parts) < 8:
                logger.error(f"Invalid ICE candidate format: {candidate_str}")
                return
            
            # Extract parameters from the candidate string
            foundation = parts[0]  # "candidate:1"
            priority = int(parts[1])  # First priority
            protocol = parts[2]  # "UDP"
            # parts[3] is another priority value, we'll use the first one
            ip = parts[4]  # IP address
            port = int(parts[5])  # Port
            # parts[6] is "typ"
            candidate_type = parts[7]  # Actual type (e.g., "host")
            
            # Default values for optional parameters
            related_address = None
            related_port = None
            tcp_type = None
            
            # Check for related address/port and tcp type (if more parts exist)
            for i in range(8, len(parts), 2):
                if i + 1 < len(parts):
                    if parts[i] == "raddr":
                        related_address = parts[i + 1]
                    elif parts[i] == "rport":
                        related_port = int(parts[i + 1])
                    elif parts[i] == "tcptype":
                        tcp_type = parts[i + 1]
            
            # Create RTCIceCandidate with the correct parameter format
            ice_candidate = RTCIceCandidate(
                component=1,  # Default to 1 for RTP
                foundation=foundation,
                ip=ip,
                port=port,
                priority=priority,
                protocol=protocol,
                type=candidate_type,
                relatedAddress=related_address,
                relatedPort=related_port,
                sdpMid=candidate.get("sdpMid"),
                sdpMLineIndex=candidate.get("sdpMLineIndex"),
                tcpType=tcp_type
            )
            
            await pc.addIceCandidate(ice_candidate)
            logger.info(f"Successfully added ICE candidate for peer {peer_id}")
            
        except Exception as e:
            logger.error(f"Error adding ICE candidate for peer {peer_id}: {e}")
            logger.error(f"Candidate data received: {candidate}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def remove_peer(self, peer_id: str):
        """Clean up peer connection and associated resources"""
        if peer_id in self.connections:
            pc = self.connections[peer_id]
            await pc.close()
            del self.connections[peer_id]
            
        if peer_id in self.audio_tracks:
            del self.audio_tracks[peer_id]
            
        # Stop any active recordings
        await self.audio_handler.stop_recording(peer_id)
        
        self.room.leave(peer_id)
        logger.info(f"Cleaned up resources for peer {peer_id}")

    def get_audio_track(self, peer_id: str) -> Optional[MediaStreamTrack]:
        """Get the audio track for a specific peer"""
        return self.audio_tracks.get(peer_id)

    def get_active_audio_peers(self) -> Set[str]:
        """Get all peer IDs that have active audio tracks"""
        return set(self.audio_tracks.keys())
    
    def register_custom_audio_processor(self, name: str, processor):
        """Register a custom audio processor"""
        self.audio_handler.register_audio_processor(name, processor)
        logger.info(f"Registered custom audio processor: {name}")

    def get_peers_in_room(self, room_id: str) -> Set[str]:
        """Get all peer IDs in a specific room"""
        return self.room.get_peers_in_room(room_id)

    def get_ice_connection_state(self, peer_id: str) -> Dict:
        """Get ICE connection state information for a specific peer"""
        if peer_id not in self.connections:
            return {"error": "Peer not found"}
        
        pc = self.connections[peer_id]
        return {
            "peer_id": peer_id,
            "connection_state": pc.connectionState,
            "ice_connection_state": pc.iceConnectionState,
            "ice_gathering_state": pc.iceGatheringState,
            "signaling_state": pc.signalingState
        }

    def get_audio_streaming_status(self, room_id: str = None) -> Dict:
        """Get detailed audio streaming status for debugging"""
        status = {
            "total_connections": len(self.connections),
            "total_audio_tracks": len(self.audio_tracks),
            "active_rooms": len(self.room.rooms),
            "audio_statistics": self.get_all_audio_statistics()
        }
        
        if room_id:
            room_peers = self.room.get_peers_in_room(room_id)
            status["room_info"] = {
                "room_id": room_id,
                "total_peers": len(room_peers),
                "peers": list(room_peers),
                "peers_with_audio": [peer_id for peer_id in room_peers if peer_id in self.audio_tracks],
                "peers_with_connections": [peer_id for peer_id in room_peers if peer_id in self.connections]
            }
        
        return status




class AudioPlayerTrack:
    def __init__(self, track: MediaStreamTrack, target_rate: int = 48000, buffer_seconds: float = 0.3):
        """
        Play an incoming WebRTC MediaStreamTrack locally with smooth audio.

        :param track: incoming MediaStreamTrack (audio)
        :param target_rate: playback sample rate (usually 48000 for WebRTC)
        :param buffer_seconds: how much audio to buffer (0.2–0.5 recommended)
        """
        self.track = track
        self.target_rate = target_rate
        self.channels = 2  # force stereo output
        self.buffer = deque()
        self.buffer_size = int(target_rate * buffer_seconds)
        self._task = None
        self._stopped = asyncio.Event()
        self.stream = None

    def start(self):
        """Start playback in background"""
        # Create the sounddevice stream but don't start immediately
        self.stream = sd.OutputStream(
            samplerate=self.target_rate,
            channels=self.channels,
            dtype='float32',
            callback=self._audio_callback,
            blocksize=1024,
        )

        # Start pulling frames
        self._task = asyncio.create_task(self._run())

        # Start the stream after pre-filling some audio
        asyncio.create_task(self._warmup())

    async def stop(self):
        """Stop playback"""
        self._stopped.set()
        if self._task:
            await self._task
        if self.stream:
            self.stream.stop()
            self.stream.close()

    async def _warmup(self):
        """Allow buffer to fill before starting playback"""
        await asyncio.sleep(0.2)  # 200ms pre-buffer
        if not self._stopped.is_set() and self.stream:
            self.stream.start()

    async def _run(self):
        """Background: pull frames from WebRTC track and buffer them"""
        try:
            while not self._stopped.is_set():
                frame: AudioFrame = await self.track.recv()

                pcm = frame.to_ndarray()   # shape: (channels, samples)
                pcm = np.transpose(pcm)    # → (samples, channels)

                # Fix 1: normalize correctly depending on dtype
                if pcm.dtype == np.int16:
                    pcm = pcm.astype(np.float32) / 32768.0
                elif pcm.dtype != np.float32:
                    pcm = pcm.astype(np.float32)

                # Fix 2: handle mono → duplicate to stereo
                if pcm.shape[1] == 1:
                    pcm = np.repeat(pcm, 2, axis=1)

                # Add samples to ring buffer
                for sample in pcm:
                    self.buffer.append(sample)

                # Trim buffer if too big
                while len(self.buffer) > self.buffer_size:
                    self.buffer.popleft()

        except Exception as e:
            print(f"Audio player error: {e}")

    def _audio_callback(self, outdata, frames, time, status):
        """Sounddevice realtime callback"""
        chunk = []
        for _ in range(frames):
            if self.buffer:
                chunk.append(self.buffer.popleft())
            else:
                # Fix 3: silence if underrun
                chunk.append([0.0] * self.channels)

        outdata[:] = np.array(chunk, dtype=np.float32)