import asyncio
import socket
import struct
import time

async def test_stun_server(host, port):
    """Test individual STUN server connectivity"""
    try:
        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)
        
        # STUN Binding Request message
        # Message Type: Binding Request (0x0001)
        # Message Length: 0 (no attributes)
        # Magic Cookie: 0x2112A442
        # Transaction ID: 12 random bytes
        msg_type = struct.pack('!H', 0x0001)
        msg_length = struct.pack('!H', 0x0000)
        magic_cookie = struct.pack('!L', 0x2112A442)
        transaction_id = b'\x00' * 12
        
        stun_request = msg_type + msg_length + magic_cookie + transaction_id
        
        print(f"Testing STUN server {host}:{port}...")
        start_time = time.time()
        
        sock.sendto(stun_request, (host, port))
        response, addr = sock.recvfrom(1024)
        
        elapsed = time.time() - start_time
        print(f"✅ {host}:{port} responded in {elapsed:.3f}s (response length: {len(response)} bytes)")
        sock.close()
        return True
        
    except socket.timeout:
        print(f"❌ {host}:{port} - Timeout (no response)")
        return False
    except socket.gaierror as e:
        print(f"❌ {host}:{port} - DNS resolution failed: {e}")
        return False
    except Exception as e:
        print(f"❌ {host}:{port} - Error: {e}")
        return False
    finally:
        try:
            sock.close()
        except:
            pass

async def test_all_stun_servers():
    """Test all your STUN servers"""
    stun_servers = [
        ("stun.l.google.com", 19302),
        ("stun1.l.google.com", 19302),
        ("stun2.l.google.com", 19302),
        ("stun3.l.google.com", 19302),
        ("stun4.l.google.com", 19302),
        ("stun.stunprotocol.org", 3478),
        ("stun1.opentelecom.ro", 3478),
        # Additional reliable STUN servers to try
        ("stun.cloudflare.com", 3478),
        ("openrelay.metered.ca", 80),
    ]
    
    print("Testing STUN server connectivity...\n")
    
    working_servers = []
    for host, port in stun_servers:
        if await test_stun_server(host, port):
            working_servers.append((host, port))
        await asyncio.sleep(0.1)  # Small delay between tests
    
    print(f"\nSummary: {len(working_servers)}/{len(stun_servers)} STUN servers are reachable")
    
    if working_servers:
        print("Working STUN servers:")
        for host, port in working_servers:
            print(f"  - stun:{host}:{port}")
    else:
        print("⚠️  No STUN servers are reachable - this will prevent ICE gathering!")
    
    return working_servers

# Run the test
if __name__ == "__main__":
    asyncio.run(test_all_stun_servers())