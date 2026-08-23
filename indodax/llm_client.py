"""
Client Integrasi AI / Large Language Model (LLM) untuk Analisis Pasar Crypto

Menghubungkan bot dengan model kecerdasan buatan (seperti LongCat-2.0 / OpenAI API compatible)
untuk mengevaluasi sentimen momentum teknikal, mengonfirmasi multi-indikator, dan memberikan
alasan (reasoning) rasional sebelum keputusan trading dieksekusi.

Fitur:
- Exponential backoff automatic retry untuk mengantisipasi network glitch / rate limiting.
- Structured JSON output parsing (Signal, Confidence, Reasoning, Risk Level).
- Fallback keyword extraction jika model merespons dalam format teks bebas.

Author: AI Trading Bot
"""

import json
import logging
import time
import urllib.request
import urllib.error
import socket
from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_TIMEOUT = 15


def retry_with_backoff(func):
    """
    Decorator untuk mengulang pemanggilan API LLM jika terjadi kegagalan jaringan atau timeout.
    
    Strategi Retry:
    - Percobaan maksimal: 3x.
    - Waktu tunggu bertahap (Exponential backoff): 2s, 4s, 8s.
    
    Args:
        func (callable): Fungsi yang akan dibungkus.
        
    Returns:
        callable: Wrapper function dengan logika retry.
    """
    def wrapper(*args, **kwargs):
        """
        Inner function yang menjalankan retry logic untuk LLM API call.

        Strategy:
        - Network errors (URLError, timeout, ConnectionError): exponential backoff retry
        - HTTPError: langsung return None (tidak retry, biasanya 4xx/5xx permanent)
        - Exception lain: langsung return None

        Returns:
            str | None: Response text dari LLM, atau None jika semua retry gagal.
        """
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
                wait = (2 ** attempt) * 2
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Retry {attempt + 1}/{MAX_RETRIES} after {wait}s: {str(e)[:80]}")
                    time.sleep(wait)
                else:
                    logger.error(f"Failed after {MAX_RETRIES} retries: {str(e)[:80]}")
                    return None
            except urllib.error.HTTPError as e:
                logger.error(f"LLM API HTTP {e.code}: {str(e)[:80]}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)[:80]}")
                return None
        return None
    return wrapper


class LLMClient:
    """
    Klien HTTP untuk komunikasi dengan endpoint AI Chat Completions (OpenAI Compatible).
    
    Attributes:
        base_url (str): URL dasar API LLM.
        api_key (str): Kunci otentikasi API.
        model (str): Nama model LLM yang ditargetkan (misal 'LongCat-2.0').
        enabled (bool): Status apakah kredensial LLM terisi dan siap digunakan.
    """

    def __init__(self):
        """
        Inisialisasi LLMClient dengan kredensial dari file konfigurasi.
        """
        self.base_url = LLM_BASE_URL.rstrip("/")
        self.api_key = LLM_API_KEY
        self.model = LLM_MODEL
        self.enabled = bool(self.base_url and self.api_key)

    @retry_with_backoff
    def _call_api(self, messages, temperature=0.3, max_tokens=500):
        """
        Mengirim payload chat messages ke endpoint `/chat/completions`.
        
        Args:
            messages (list): Daftar dictionary pesan [{'role': 'system'/'user', 'content': '...'}].
            temperature (float, optional): Tingkat kreativitas model (rendah 0.3 untuk keputusan konsisten).
            max_tokens (int, optional): Batas panjang output token. Default 500.
            
        Returns:
            dict or None: Hasil parsing respons terstruktur atau None jika API non-aktif/gagal.
        """
        if not self.enabled:
            return None

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=BASE_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            message = result["choices"][0]["message"]
            content = message.get("content", "").strip()
            reasoning = message.get("reasoning_content", "")
            return self._parse_response(content, reasoning)

    def _parse_response(self, content, reasoning=""):
        """
        Mem-parse respons mentah dari LLM menjadi dictionary standar berskema.
        
        Skema output:
        - signal: 'buy', 'sell', atau 'hold'
        - confidence: 0.0 - 1.0
        - reasoning: Penjelasan singkat alasan keputusan
        - risk_level: 'low', 'medium', atau 'high'
        
        Args:
            content (str): Teks respons utama dari LLM.
            reasoning (str, optional): Teks reasoning khusus jika model mendukung CoT.
            
        Returns:
            dict: Objek terstruktur keputusan AI.
        """
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        import re
        json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        content_lower = content.lower()
        if "buy" in content_lower and "sell" not in content_lower:
            signal = "buy"
        elif "sell" in content_lower and "buy" not in content_lower:
            signal = "sell"
        elif "hold" in content_lower:
            signal = "hold"
        else:
            signal = "hold"

        return {
            "signal": signal,
            "confidence": 0.5,
            "reasoning": content[:200] if content else reasoning[:200],
            "risk_level": "medium",
        }

    def analyze_market(self, symbol, indicators, current_price):
        """
        Mengirimkan ringkasan data teknikal ke LLM untuk mendapatkan analisis sentimen pasar.
        
        Args:
            symbol (str): Simbol pair (misal 'BTC/IDR').
            indicators (dict): Nilai indikator RSI, MACD, ATR, EMA, Volume.
            current_price (float): Harga koin saat ini.
            
        Returns:
            dict or None: Evaluasi sinyal trading dari LLM.
        """
        if not self.enabled:
            return None

        system_prompt = """You are an expert cryptocurrency trading AI. Analyze the provided technical indicators and market data to generate a trading signal.

Rules:
- Consider the overall trend, momentum, volatility, and volume
- Be conservative - only signal BUY/SELL when there's clear confirmation from multiple indicators
- RSI < 30 = oversold (bullish), RSI > 70 = overbought (bearish)
- MACD histogram turning positive = bullish momentum, negative = bearish
- Price above EMA21 and EMA50 = uptrend, below = downtrend
- Price touching Bollinger lower band = potential bounce, upper band = potential reversal
- High volume confirms the signal strength

IMPORTANT: End your response with a JSON object on its own line:
{"signal": "buy" or "sell" or "hold", "confidence": 0.0-1.0, "reasoning": "brief explanation", "risk_level": "low" or "medium" or "high"}"""

        user_data = f"""
Symbol: {symbol}
Current Price: {current_price:,.2f} IDR

Technical Indicators:
- RSI (14): {indicators.get('rsi', 'N/A')}
- MACD Line: {indicators.get('macd', 'N/A')}
- MACD Signal: {indicators.get('macd_signal', 'N/A')}
- MACD Histogram: {indicators.get('macd_histogram', 'N/A')}
- ATR (14): {indicators.get('atr', 'N/A')}
- EMA 9: {indicators.get('ema_9', 'N/A')}
- EMA 21: {indicators.get('ema_21', 'N/A')}
- EMA 50: {indicators.get('ema_50', 'N/A')}
- Volume Signal: {indicators.get('volume_signal', 'N/A')}

Price vs EMAs:
- vs EMA9: {((current_price / indicators.get('ema_9', current_price)) - 1) * 100:.2f}%
- vs EMA21: {((current_price / indicators.get('ema_21', current_price)) - 1) * 100:.2f}%
- vs EMA50: {((current_price / indicators.get('ema_50', current_price)) - 1) * 100:.2f}%

What is your trading decision?"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_data},
        ]

        result = self._call_api(messages)
        if result:
            logger.info(
                f"LLM [{symbol}] Signal: {result.get('signal', 'N/A')} | "
                f"Confidence: {result.get('confidence', 'N/A')} | "
                f"Risk: {result.get('risk_level', 'N/A')}"
            )
        return result

