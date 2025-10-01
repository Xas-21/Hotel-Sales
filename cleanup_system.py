#!/usr/bin/env python
"""
System Cleanup Script
Removes unused test files, debug scripts, and documentation files while preserving core system functionality.
"""

import os
import sys

def cleanup_files():
    """Remove unused files from the system"""
    
    # Files to remove (test files, debug scripts, documentation)
    files_to_remove = [
        # Test files
        'test_actual_status_display.py',
        'test_all_periods.py', 
        'test_date_ranges.py',
        'test_dates_simple.py',
        'test_enhanced_alerts.py',
        'test_fixes.py',
        'test_notifications.py',
        'test_problematic_periods.py',
        'test_trend_chart.py',
        
        # Debug and development scripts
        'debug_calculation.py',
        'fix_database_direct.py',
        'fix_deadlines.py',
        'fix_nights_calculation.py',
        'force_recalculate.py',
        'setup_automation.py',
        'restore_original_functionality.py',
        'update_to_actual_status.py',
        
        # Documentation files (change logs)
        'ACCOUNT_PROFILE_TABLE_UPDATE.md',
        'ACTUAL_STATUS_INTEGRATION.md',
        'ALERT_PRIORITY_FIX.md',
        'ALERT_SYSTEM_FIX.md',
        'AUTO_CALCULATION_FIX.md',
        'CHANGES_SUMMARY.md',
        'CHART_COLOR_FIX.md',
        'CHART_DESIGN_REVERSION.md',
        'CHART_LINE_SEPARATION_FIX.md',
        'COMPLETE_DATE_RANGE_FIX.md',
        'COMPREHENSIVE_AUTO_CALC_FIX.md',
        'DASHBOARD_STATUS_DISPLAY_FIX.md',
        'DATE_RANGE_FIX.md',
        'ENHANCED_LINE_SEPARATION.md',
        'FINAL_CHART_FIX.md',
        'FINAL_DATE_RANGE_FIX.md',
        'NEW_TREND_CHARTS_ADDITION.md',
        'NIGHTS_CALCULATION_FIX.md',
        'REQUEST_MODEL_CONFLICT_FIX.md',
        'REQUEST_STATUS_COLOR_UPDATE.md',
        'REQUEST_STATUS_TRENDS_CHART.md',
        'RESTORED_ORIGINAL_FUNCTIONALITY.md',
        
        # Other temporary files
        'cookies.txt',
        'replit.md',
        
        # This cleanup script itself
        'cleanup_system.py',
    ]
    
    removed_files = []
    not_found_files = []
    
    print("🧹 Starting system cleanup...")
    print("=" * 50)
    
    for file_path in files_to_remove:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                removed_files.append(file_path)
                print(f"✅ Removed: {file_path}")
            except Exception as e:
                print(f"❌ Failed to remove {file_path}: {e}")
        else:
            not_found_files.append(file_path)
            print(f"ℹ️  Not found: {file_path}")
    
    print("\n" + "=" * 50)
    print(f"🎉 Cleanup completed!")
    print(f"📊 Summary:")
    print(f"  • Files removed: {len(removed_files)}")
    print(f"  • Files not found: {len(not_found_files)}")
    
    if removed_files:
        print(f"\n🗑️  Removed files:")
        for file_path in removed_files:
            print(f"    - {file_path}")
    
    if not_found_files:
        print(f"\nℹ️  Files not found (already removed or never existed):")
        for file_path in not_found_files:
            print(f"    - {file_path}")
    
    print(f"\n✅ Core system files preserved:")
    print(f"    - Django apps (accounts, requests, dashboard, etc.)")
    print(f"    - Database (db.sqlite3)")
    print(f"    - Templates and static files")
    print(f"    - Settings and configuration")
    print(f"    - Management commands")
    print(f"    - Models, views, and admin configurations")

if __name__ == "__main__":
    cleanup_files()

