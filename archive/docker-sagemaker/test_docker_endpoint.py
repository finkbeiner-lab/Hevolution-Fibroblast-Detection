"""
Test the Docker container inference endpoint locally
This sends HTTP requests to the container running on localhost:8080
"""

import requests
import json
import base64
import argparse
import sys
import os
from pathlib import Path

def test_docker_endpoint(image_path, diameter=None, denoise=False, blur=False, 
                        host='localhost', port=8080, output_dir='docker_test_results'):
    """
    Test the Docker inference endpoint
    
    Args:
        image_path: Path to input image
        diameter: Cell diameter parameter
        denoise: Whether to apply denoising
        blur: Whether to apply Gaussian blur
        host: Container host (default: localhost)
        port: Container port (default: 8080)
        output_dir: Directory to save results
    """
    endpoint_url = f"http://{host}:{port}/invocations"
    
    print("=" * 60)
    print("Docker Endpoint Test")
    print("=" * 60)
    print(f"Endpoint: {endpoint_url}")
    print()
    
    # Check if image exists
    if not os.path.exists(image_path):
        print(f"❌ Image file not found: {image_path}")
        sys.exit(1)
    
    # Prepare payload
    print("📥 Preparing request...")
    
    # Verify image file exists and is readable
    if not os.path.exists(image_path):
        print(f"❌ Image file not found: {image_path}")
        sys.exit(1)
    
    file_size = os.path.getsize(image_path)
    print(f"   Image file size: {file_size:,} bytes")
    
    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    
    if len(image_bytes) == 0:
        print(f"❌ Image file is empty: {image_path}")
        sys.exit(1)
    
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    print(f"   Base64 encoded length: {len(image_b64):,} characters")
    
    if len(image_b64) < 100:
        print(f"⚠️  Warning: Base64 string is very short ({len(image_b64)} chars). Image might be corrupted.")
    
    payload = {
        'image': image_b64,
        'diameter': diameter,
        'denoise': denoise,
        'blur': blur
    }
    
    # Verify payload
    payload_json = json.dumps(payload)
    print(f"   Payload JSON size: {len(payload_json):,} characters")
    print(f"   Image in payload length: {len(payload.get('image', '')):,} characters")
    
    print(f"   Image: {image_path}")
    print(f"   Parameters: diameter={diameter}, denoise={denoise}, blur={blur}")
    print()
    
    # Check if endpoint is accessible first
    print("🔍 Checking if endpoint is accessible...")
    try:
        # Try a simple GET request to ping endpoint (with longer timeout)
        ping_response = requests.get(f"http://{host}:{port}/ping", timeout=10)
        print(f"   ✅ Endpoint is reachable (ping: {ping_response.status_code})")
    except requests.exceptions.ConnectionError:
        print("   ❌ Cannot connect to endpoint")
        print("")
        print("Troubleshooting:")
        print("   1. Check if container is running:")
        print("      docker ps | grep fibroblast-detection-test")
        print("")
        print("   2. Check container logs:")
        print("      docker logs fibroblast-detection-test")
        print("")
        print("   3. Start/restart the container:")
        print("      ./test_docker_local.sh")
        print("")
        print("   4. Check if port 8080 is in use:")
        print("      lsof -i :8080")
        sys.exit(1)
    except Exception as e:
        print(f"   ⚠️  Could not ping endpoint: {e}")
        print("   Continuing anyway...")
    
    # Send request
    print("")
    print("🚀 Sending inference request...")
    try:
        response = requests.post(
            endpoint_url,
            json=payload,
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            timeout=300  # 5 minute timeout for inference
        )
        
        response.raise_for_status()
        
        print("✅ Request successful")
        print()
        
        # Parse response
        results = response.json()
        
        # Save results
        print("💾 Saving results...")
        os.makedirs(output_dir, exist_ok=True)
        
        # Save statistics
        stats = results.get('statistics', {})
        stats_path = os.path.join(output_dir, 'statistics.json')
        with open(stats_path, 'w') as f:
            json.dump(stats, f, indent=2)
        print(f"   Saved: {stats_path}")
        
        # Save images
        for img_name in ['normalized_image', 'segmentation_mask', 'intensity_histogram']:
            if img_name in results:
                img_data = base64.b64decode(results[img_name])
                img_path = os.path.join(output_dir, f'{img_name}.png')
                with open(img_path, 'wb') as f:
                    f.write(img_data)
                print(f"   Saved: {img_path}")
        
        # Print statistics
        print()
        print("=" * 60)
        print("Results Summary")
        print("=" * 60)
        print(f"Cell Count: {stats.get('cell_count', 'N/A')}")
        print(f"Confluency: {stats.get('confluency', 'N/A'):.2f}%")
        print(f"Min Intensity: {stats.get('min_intensity', 'N/A')}")
        print(f"Max Intensity: {stats.get('max_intensity', 'N/A')}")
        print(f"\n✅ All results saved to: {output_dir}/")
        print("=" * 60)
        
        return results
        
    except requests.exceptions.ConnectionError as e:
        print("❌ Connection failed")
        print(f"   Error: {e}")
        print("")
        print("The container may not be running. Try:")
        print("   1. Check container status: ./check_container.sh")
        print("   2. Start container: ./test_docker_local.sh")
        print("   3. Check logs: docker logs fibroblast-detection-test")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("❌ Request timed out (inference took > 5 minutes)")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP error: {e}")
        print(f"   Response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Test Docker inference endpoint locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic test (container must be running)
  python test_docker_endpoint.py image.jpg
  
  # With custom parameters
  python test_docker_endpoint.py image.jpg --diameter 30 --denoise --blur
  
  # Custom host/port
  python test_docker_endpoint.py image.jpg --host localhost --port 8080
        """
    )
    
    parser.add_argument('image_path', type=str, help='Path to input image file')
    parser.add_argument('--diameter', type=float, default=None, 
                       help='Approximate cell diameter (default: auto-detect)')
    parser.add_argument('--denoise', action='store_true', 
                       help='Apply denoising preprocessing')
    parser.add_argument('--blur', action='store_true', 
                       help='Apply Gaussian blur preprocessing')
    parser.add_argument('--host', type=str, default='localhost',
                       help='Container host (default: localhost)')
    parser.add_argument('--port', type=int, default=8080,
                       help='Container port (default: 8080)')
    parser.add_argument('--output-dir', type=str, default='docker_test_results',
                       help='Directory to save results (default: docker_test_results)')
    
    args = parser.parse_args()
    
    test_docker_endpoint(
        args.image_path,
        diameter=args.diameter,
        denoise=args.denoise,
        blur=args.blur,
        host=args.host,
        port=args.port,
        output_dir=args.output_dir
    )

if __name__ == "__main__":
    main()
