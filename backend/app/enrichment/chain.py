"""chain worker：攻击链推演（确定性模板 + LLM 润色）"""
from __future__ import annotations

from app.core.logging import get_logger
from app.enrichment.common import llm_enabled, llm_text, ok, skipped

log = get_logger("enrich.chain")

# CWE → 攻击链模板（确定式骨架，LLM 仅用于措辞）
CWE_CHAIN = {
    "CWE-78": ["初始访问: 注入 OS 命令", "执行: 远程命令执行", "影响: 服务器接管"],
    "CWE-89": ["初始访问: SQL 注入", "执行: 数据库读写", "横向: 提权/数据窃取", "影响: 数据泄露"],
    "CWE-79": ["投递: 恶意脚本注入", "执行: XSS 会话劫持", "影响: 账号接管"],
    "CWE-502": ["初始访问: 恶意序列化数据", "执行: 反序列化 RCE", "影响: 服务器接管"],
    "CWE-22": ["初始访问: 路径穿越", "执行: 任意文件读写", "影响: 信息泄露/RCE"],
    "CWE-918": ["初始访问: SSRF", "执行: 内网探测/云凭证窃取", "影响: 内网渗透"],
    "CWE-434": ["投递: 恶意文件上传", "执行: Webshell/RCE", "影响: 持久化"],
    "CWE-94": ["初始访问: 代码注入", "执行: 任意代码执行", "影响: 服务器接管"],
    "CWE-611": ["初始访问: XXE", "执行: 文件读取/SSRF", "影响: 信息泄露"],
    "CWE-287": ["初始访问: 认证绕过", "执行: 未授权操作", "影响: 权限提升"],
    "CWE-306": ["初始访问: 缺失认证", "执行: 未授权 API 调用", "影响: 数据/控制权暴露"],
}
AI_LAYER_CHAIN = {
    "L1": ["入口: 恶意 Prompt/插件/数据源", "攻击: 提示注入→越权调用", "影响: 数据外泄/Agent 劫持"],
    "L2": ["入口: 恶意模型权重/供应链", "攻击: 加载即执行/后门", "影响: 训练/推理环境接管"],
    "L3": ["入口: 框架组件漏洞", "攻击: RCE/反序列化", "影响: AI 服务接管"],
    "L4": ["入口: 未授权/配置错误", "攻击: 数据/模型窃取", "影响: IP 泄露"],
    "L5": ["入口: 系统服务漏洞", "攻击: 权限提升", "影响: 平台接管"],
    "L6": ["入口: 滥用/误用", "攻击: 生成恶意内容", "影响: 社会工程/滥用"],
}


async def run(item, ctx) -> dict:
    cwes = item.cwe_ids or []
    layers = [item.ai_layer] if item.ai_layer else []
    chain: list[str] = []
    for cwe in cwes:
        if cwe in CWE_CHAIN:
            chain = CWE_CHAIN[cwe]
            break
    if not chain:
        for l in layers:
            if l in AI_LAYER_CHAIN:
                chain = AI_LAYER_CHAIN[l]
                break
    if not chain and (item.cvss_v31_vector or "").find("AV:N") >= 0:
        chain = ["入口: 网络可达组件", "攻击: 远程利用", "影响: 组件失陷"]
    if not chain:
        return skipped("no chain basis")

    chain_text = " → ".join(chain)
    chain_json = {"format": "attack-flow-lite",
                  "steps": [{"stage": s.split(":")[0].strip(), "desc": s.split(":", 1)[-1].strip()} for s in chain]}
    extra = {"attack_chain_text": chain_text}

    # LLM 润色为一段攻击路径描述（可选）
    desc = None
    if llm_enabled():
        desc = await llm_text(
            [{"role": "system", "content": "用 60-120 字中文描述该漏洞的可能攻击路径，风格类似 ATT&CK 战术链描述，客观不夸张。"},
             {"role": "user", "content": f"漏洞：{item.title}\n链：{chain_text}\n摘要：{(item.summary or '')[:400]}"}],
            max_tokens=300)
    if desc:
        extra["attack_chain_desc"] = desc[:400]

    return ok(f"chain={len(chain)}", confidence=0.7,
              fields={"attack_chain": chain_json}, extra=extra, data_keys=["chain"])
