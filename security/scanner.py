"""Vulnerability Scanner"""
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

import re

from security.errors import ScanError


# Known vulnerability patterns
VULNERABILITY_PATTERNS = {
    "sql_injection": re.compile(r"(?:')|(--)|(/\*)|(\*/)|(xp_)", re.IGNORECASE),
    "xss": re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL),
    "hardcoded_password": re.compile(r"(?:password|passwd|secret)\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE),
    "api_key": re.compile(r"(?:api_key|apikey|token)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]", re.IGNORECASE),
}


class VulnerabilityScanner:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._scans = []
                cls._instance._lock = threading.Lock()
            return cls._instance
    
    def scan_code(self, code: str, file_path: str = None) -> List[Dict[str, Any]]:
        """Scan code for vulnerabilities."""
        vulnerabilities = []
        
        for vuln_type, pattern in VULNERABILITY_PATTERNS.items():
            for match in pattern.finditer(code):
                vulnerabilities.append({
                    "vulnerability_id": str(uuid.uuid4()),
                    "type": vuln_type,
                    "severity": "high",
                    "file_path": file_path,
                    "line": code[:match.start()].count("\n") + 1,
                    "match": match.group(),
                    "description": f"Potential {vuln_type.replace('_', ' ')} vulnerability",
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                })
        
        return vulnerabilities
    
    def scan_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Scan a file for vulnerabilities."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            return self.scan_code(code, file_path)
        except Exception as e:
            raise ScanError(f"Failed to scan file: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scanning statistics."""
        with self._lock:
            scans = list(self._scans)
        
        return {
            "total_scans": len(scans),
            "total_vulnerabilities": sum(len(s.get("vulnerabilities", [])) for s in scans),
        }


def get_vulnerability_scanner():
    return VulnerabilityScanner()


def reset_vulnerability_scanner():
    VulnerabilityScanner._instance = None
