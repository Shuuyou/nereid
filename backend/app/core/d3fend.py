"""D3FEND 缓解对策映射：ATT&CK 技术 → D3FEND 防御技术（MITRE 防御知识图谱）"""
from __future__ import annotations

# ATT&CK tech_id → [(d3fend_id, 名称, 说明)]
D3FEND_MAP: dict[str, list[tuple[str, str, str]]] = {
    "T1190": [("D3-OTF", "Outbound Traffic Filtering", "限制出站连接阻断回连"),
              ("D3-WCF", "Web Content Filtering", "WAF 规则拦截注入/RCE"),
              ("D3-UA", "URL Analysis", "URL 信誉/沙箱分析")],
    "T1059": [("D3-PSA", "Process Spawn Analysis", "监控异常进程派生链"),
              ("D3-PLA", "Process Lineage Analysis", "父子进程血缘审计"),
              ("D3-SDA", "System Daemon Analysis", "守护进程行为基线")],
    "T1059.007": [("D3-PSA", "Process Spawn Analysis", "JS/脚本执行进程监控")],
    "T1105": [("D3-NTF", "Network Traffic Filtering", "文件传输通道指纹/阻断"),
              ("D3-FA", "File Analysis", "落地文件静态/沙箱检测")],
    "T1496": [("D3-RAPA", "Resource Access Pattern Analysis", "资源占用异常检测（挖矿）"),
              ("D3-NTA", "Network Traffic Analysis", "矿池协议流量识别")],
    "T1078": [("D3-UAA", "User Account Analysis", "账号行为异常（UEBA）"),
              ("D3-MFA", "Multi-factor Authentication", "多因素认证")],
    "T1552": [("D3-SCA", "Secure Configuration Analysis", "凭据明文配置审计")],
    "T1210": [("D3-SVA", "Software Vulnerability Assessment", "持续漏洞扫描与补丁")],
    "T1027": [("D3-FH", "File Hashing", "已知恶意哈希库比对"),
              ("D3-DL", "Decoy File", "诱捕文件触发告警")],
    "T1562": [("D3-TA", "Telemetry Analysis", "防御关闭行为遥测告警")],
    "T1574": [("D3-DLL", "DLL Analysis", "DLL 侧加载/劫持检测")],
    "T1041": [("D3-ETF", "Encrypted Traffic Filtering", "C2 加密通道指纹"),
              ("D3-DNS", "DNS Analysis", "DNS 隧道检测")],
    "T1567": [("D3-DTP", "Data Transfer Prevention", "数据外传通道管控(DLP)")],
    "T1195": [("D3-SPP", "Supply Chain Protection", "供应链组件签名校验(SBOM)")],
    "T1185": [("D3-SE", "Session Analysis", "浏览器会话/中间人检测")],
}


def mitigations_for(techniques: list[str] | None) -> list[dict]:
    """ATT&CK 技术列表 → D3FEND 对策（去重）"""
    out: list[dict] = []
    seen: set[str] = set()
    for t in techniques or []:
        base = t.split(".")[0]
        for did, name, desc in (D3FEND_MAP.get(t) or D3FEND_MAP.get(base) or []):
            if did not in seen:
                seen.add(did)
                out.append({"id": did, "name": name, "desc": desc, "for_technique": t})
    return out[:8]
