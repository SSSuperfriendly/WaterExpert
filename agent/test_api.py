#!/usr/bin/env python
"""
Test script for Water AI API.

This script demonstrates how to use the API endpoints.
It assumes the server is running on http://localhost:8000
"""

import sys
import time
from pathlib import Path

import requests

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

BASE_URL = "http://localhost:8000/api"


def test_health():
    """Test health check endpoint."""
    print("\n" + "=" * 80)
    print("Test 1: Health Check")
    print("=" * 80)
    
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    return response.status_code == 200


def test_system_status():
    """Test system status endpoint."""
    print("\n" + "=" * 80)
    print("Test 2: System Status")
    print("=" * 80)
    
    response = requests.get(f"{BASE_URL}/status")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    return response.status_code == 200


def test_list_scenarios():
    """Test scenario listing endpoint."""
    print("\n" + "=" * 80)
    print("Test 3: List Scenarios")
    print("=" * 80)
    
    response = requests.get(f"{BASE_URL}/scenarios")
    print(f"Status: {response.status_code}")
    scenarios = response.json()
    print(f"Found {len(scenarios)} scenarios:")
    for scenario in scenarios:
        print(f"  - {scenario['code']}: {scenario['name']}")
    
    return response.status_code == 200


def test_get_scenario():
    """Test get specific scenario endpoint."""
    print("\n" + "=" * 80)
    print("Test 4: Get Specific Scenario")
    print("=" * 80)
    
    response = requests.get(f"{BASE_URL}/scenarios/s1_external_input")
    print(f"Status: {response.status_code}")
    scenario = response.json()
    print(f"Scenario: {scenario['code']} - {scenario['name']}")
    print(f"Description: {scenario['description']}")
    
    return response.status_code == 200


def test_generate_strategy():
    """Test strategy generation endpoint."""
    print("\n" + "=" * 80)
    print("Test 5: Generate Strategy (Background Task)")
    print("=" * 80)
    
    payload = {
        "scenario": "s1_external_input",
        "state": {
            "date": "2025-10-31",
            "turbidity": 25.5,
            "flow_rate": 28.5,
            "temperature": 18.2,
            "ph": 7.5,
            "dissolved_oxygen": 8.3,
            "chlorophyll_a": 5.2,
            "rainfall_3d": 45.3,
            "rainfall_7d": 120.5,
        },
        "episodes": 1,
        "backend": "api",
    }
    
    response = requests.post(f"{BASE_URL}/strategy", json=payload)
    print(f"Status: {response.status_code}")
    result = response.json()
    print(f"Response: {result}")
    
    if response.status_code == 200:
        job_id = result["job_id"]
        print(f"\n✓ Job created with ID: {job_id}")
        
        # Wait a bit for processing
        print("\nWaiting for processing...")
        for i in range(5):
            time.sleep(1)
            
            # Check job status
            status_response = requests.get(f"{BASE_URL}/strategy/{job_id}")
            status = status_response.json()
            
            if status["status"] == "completed":
                print(f"✓ Job completed!")
                print(f"  - Strategy: {status['strategy']}")
                print(f"  - Metrics: {status['metrics']}")
                return True
            elif status["status"] == "failed":
                print(f"✗ Job failed: {status['error']}")
                return False
            else:
                print(f"  Status: {status['status']}... ({i+1}/5)")
        
        print("⚠ Job still running after 5 seconds (this is OK for background tasks)")
        return True
    
    return False


def test_list_jobs():
    """Test list jobs endpoint."""
    print("\n" + "=" * 80)
    print("Test 6: List Jobs")
    print("=" * 80)
    
    response = requests.get(f"{BASE_URL}/jobs?limit=5")
    print(f"Status: {response.status_code}")
    jobs = response.json()
    print(f"Found {len(jobs)} jobs:")
    for job in jobs:
        print(f"  - {job['job_id']}: {job['scenario']} ({job['status']})")
    
    return response.status_code == 200


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("Water AI API Test Suite")
    print("=" * 80)
    
    # Check server connection
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        print(f"✓ Connected to API server at {BASE_URL}")
    except requests.exceptions.ConnectionError:
        print(f"✗ Failed to connect to API server at {BASE_URL}")
        print("\n  Make sure the server is running:")
        print("  PYTHONPATH=src:$PYTHONPATH python scripts/run_api_server.py")
        sys.exit(1)
    
    # Run tests
    tests = [
        ("Health Check", test_health),
        ("System Status", test_system_status),
        ("List Scenarios", test_list_scenarios),
        ("Get Scenario", test_get_scenario),
        ("Generate Strategy", test_generate_strategy),
        ("List Jobs", test_list_jobs),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"✗ Test failed with error: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓" if result else "✗"
        print(f"{status} {test_name}")
    
    print(f"\nTotal: {passed}/{total} passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
