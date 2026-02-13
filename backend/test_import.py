#!/usr/bin/env python3
"""Test imports without running uvicorn"""
import sys

# Test critical imports
try:
    from app.services.sync_service import SyncService
    print("✅ SyncService import OK")
    
    from app.services.reconciliation_service import ReconciliationService
    print("✅ ReconciliationService import OK")
    
    print("\n✅ ALL IMPORTS SUCCESSFUL!")
    sys.exit(0)
    
except ImportError as e:
    print(f"❌ Import Error: {e}")
    sys.exit(1)
