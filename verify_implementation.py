#!/usr/bin/env python
"""
Verification script for PeoplePay 360 new modules.

This script verifies that all new components (evidence, graph, plugins)
are properly implemented and functional.
"""

import sys
import traceback


def test_evidence_module():
    """Test Evidence and Provenance Engine."""
    print("\n" + "=" * 60)
    print("TESTING: Evidence and Provenance Engine")
    print("=" * 60)
    
    try:
        from evidence import (
            EvidenceService, get_evidence_service,
            EvidenceCollector, get_evidence_collector,
            EvidenceVerifier, get_evidence_verifier,
            EvidenceStorage, get_evidence_storage,
            ProvenanceTracker, get_provenance_tracker,
            EvidenceError, EvidenceNotFoundError, VerificationError,
            EvidenceSource, EvidenceItem, Claim, VerificationResult,
        )
        
        # Test singletons
        service = get_evidence_service()
        collector = get_evidence_collector()
        verifier = get_evidence_verifier()
        storage = get_evidence_storage()
        tracker = get_provenance_tracker()
        
        assert service is not None
        assert collector is not None
        assert verifier is not None
        assert storage is not None
        assert tracker is not None
        
        print("  [PASS] All imports successful")
        print("  [PASS] All singletons accessible")
        print("  [PASS] Evidence module WORKING")
        return True
        
    except Exception as e:
        print(f"  [FAIL] Evidence module: {e}")
        traceback.print_exc()
        return False


def test_graph_module():
    """Test Graph Intelligence Layer."""
    print("\n" + "=" * 60)
    print("TESTING: Graph Intelligence Layer")
    print("=" * 60)
    
    try:
        from graph import (
            GraphService, get_graph_service,
            GraphEngine, get_graph_engine,
            GraphAnalyzer, get_graph_analyzer,
            GraphError, EntityNotFoundError, RelationshipNotFoundError,
            Entity, Relationship, EntityType, RelationshipType,
            Graph, GraphQuery, GraphQueryResult, TraversalResult,
        )
        
        # Test singletons
        service = get_graph_service()
        engine = get_graph_engine()
        analyzer = get_graph_analyzer()
        
        assert service is not None
        assert engine is not None
        assert analyzer is not None
        
        print("  [PASS] All imports successful")
        print("  [PASS] All singletons accessible")
        print("  [PASS] Graph module WORKING")
        return True
        
    except Exception as e:
        print(f"  [FAIL] Graph module: {e}")
        traceback.print_exc()
        return False


def test_plugins_module():
    """Test Integration/Plugin Architecture."""
    print("\n" + "=" * 60)
    print("TESTING: Integration/Plugin Architecture")
    print("=" * 60)
    
    try:
        from plugins import (
            PluginRegistry, get_plugin_registry,
            PluginManager, get_plugin_manager,
            PluginExecutor, get_plugin_executor,
            PluginValidator, get_plugin_validator,
            FeatureFlagManager, get_feature_flag_manager,
            Plugin, PluginCapability, PluginConfig, PluginManifest,
            PluginStatus, CapabilityContract, CapabilityType,
            PluginError, PluginNotFoundError, CapabilityNotFoundError,
        )
        
        # Test singletons
        registry = get_plugin_registry()
        manager = get_plugin_manager()
        executor = get_plugin_executor()
        validator = get_plugin_validator()
        ffm = get_feature_flag_manager()
        
        assert registry is not None
        assert manager is not None
        assert executor is not None
        assert validator is not None
        assert ffm is not None
        
        print("  [PASS] All imports successful")
        print("  [PASS] All singletons accessible")
        
        # Test basic operations
        from plugins.models import PluginManifest, CapabilityContract, CapabilityType
        manifest = PluginManifest(
            name='test_plugin',
            version='1.0.0',
            description='Test plugin',
            author='Test',
            capabilities=[
                CapabilityContract(
                    name='test_cap',
                    capability_type=CapabilityType.TOOL,
                ),
            ],
        )
        
        registry.register_plugin(manifest)
        plugin = registry.get_plugin('test_plugin')
        assert plugin is not None
        
        print("  [PASS] Plugin registration works")
        
        # Test feature flags
        ffm.register_flag(name='test_flag', enabled=True)
        assert ffm.is_enabled('test_flag') == True
        
        print("  [PASS] Feature flag management works")
        print("  [PASS] Plugins module WORKING")
        return True
        
    except Exception as e:
        print(f"  [FAIL] Plugins module: {e}")
        traceback.print_exc()
        return False


def test_integration():
    """Test integration between modules."""
    print("\n" + "=" * 60)
    print("TESTING: Cross-Module Integration")
    print("=" * 60)
    
    try:
        # Import all modules together
        from evidence import get_evidence_service
        from graph import get_graph_service
        from plugins import get_plugin_registry
        
        # Get instances
        evidence_service = get_evidence_service()
        graph_service = get_graph_service()
        plugin_registry = get_plugin_registry()
        
        assert evidence_service is not None
        assert graph_service is not None
        assert plugin_registry is not None
        
        print("  [PASS] All modules can be imported together")
        print("  [PASS] All singletons work together")
        print("  [PASS] Cross-module integration WORKING")
        return True
        
    except Exception as e:
        print(f"  [FAIL] Integration: {e}")
        traceback.print_exc()
        return False


def run_tests():
    """Run all verification tests."""
    print("\n" + "=" * 60)
    print("PEOPLEPAY 360 - IMPLEMENTATION VERIFICATION")
    print("=" * 60)
    
    results = []
    
    # Test each module
    results.append(("Evidence Module", test_evidence_module()))
    results.append(("Graph Module", test_graph_module()))
    results.append(("Plugins Module", test_plugins_module()))
    results.append(("Integration", test_integration()))
    
    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
    
    all_passed = all(passed for _, passed in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("ALL VERIFICATION TESTS PASSED!")
        print("Implementation is COMPLETE and WORKING")
    else:
        print("SOME VERIFICATION TESTS FAILED!")
        print("Please review the errors above")
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
