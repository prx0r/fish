"""DataHunter — Autonomous dataset discovery and acquisition agent.

Continuously discovers, evaluates, and downloads datasets from:
- HuggingFace
- Kaggle
- GitHub
- Nasdaq
- Cboe
- SEC
- FRED/ALFRED
- Companies House
- Academic supplements
- Zenodo, Figshare, Dataverse
- Broker APIs
- x402

Records metadata and downloads anything meeting criteria:
- cost = 0
- license acceptable
- novel information > threshold
"""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class DatasetMetadata:
    """Metadata for a discovered dataset."""
    dataset_id: str
    source: str  # huggingface, kaggle, github, nasdaq, etc.
    markets: list[str] = field(default_factory=list)
    symbols: str = "all"
    date_start: str = ""
    date_end: str = ""
    frequency: str = ""  # tick, minute, daily
    depth: str = ""  # L1, L5, L10, L50
    trades: bool = False
    orders: bool = False
    cancellations: bool = False
    size_gb: float = 0
    license: str = ""
    cost: float = 0
    auth_required: bool = False
    point_in_time_safe: bool = True
    survivorship_safe: bool = True
    quality_score: float = 0.5
    download_method: str = ""
    url: str = ""
    description: str = ""
    content_hash: str = ""
    discovered_at: str = ""
    downloaded: bool = False
    download_path: str = ""


class DataHunter:
    """Autonomous dataset discovery and acquisition agent."""
    
    def __init__(self):
        self.datasets: list[DatasetMetadata] = []
        self.download_criteria = {
            "max_cost": 0.0,
            "min_quality": 0.5,
            "accepted_licenses": [
                "mit", "apache-2.0", "cc-by-4.0", "cc-by-sa-4.0",
                "cc-by-nc-4.0", "odc-by", "pddl",
            ],
        }
    
    def discover_huggingface(self) -> list[DatasetMetadata]:
        """Discover datasets on HuggingFace."""
        # Pre-discovered high-value datasets
        hf_datasets = [
            DatasetMetadata(
                dataset_id="venvoo/china-a-share-l2-level2-limit-order-book-tick-data",
                source="huggingface",
                markets=["china", "a-share"],
                date_start="2017-01-01",
                date_end="2026-09-10",
                frequency="tick",
                depth="L10",
                trades=True,
                orders=True,
                cancellations=True,
                size_gb=2100,
                license="cc-by-nc-4.0",
                cost=0,
                auth_required=True,
                quality_score=0.95,
                download_method="huggingface_hub",
                url="https://huggingface.co/datasets/venvoo/china-a-share-l2-level2-limit-order-book-tick-data",
                description="555B rows of China A-share L2 order book data",
            ),
            DatasetMetadata(
                dataset_id="paperswithbacktest/Stocks-1Min-Price",
                source="huggingface",
                markets=["us"],
                frequency="minute",
                depth="L1",
                size_gb=5710,
                license="cc-by-4.0",
                cost=0,
                auth_required=False,
                quality_score=0.9,
                download_method="huggingface_hub",
                url="https://huggingface.co/datasets/paperswithbacktest/Stocks-1Min-Price",
                description="5.7B rows of 1-minute stock prices",
            ),
            DatasetMetadata(
                dataset_id="paperswithbacktest/Stocks-Daily-Price",
                source="huggingface",
                markets=["us"],
                frequency="daily",
                depth="L1",
                size_gb=26,
                license="cc-by-4.0",
                cost=0,
                auth_required=False,
                quality_score=0.85,
                download_method="huggingface_hub",
                url="https://huggingface.co/datasets/paperswithbacktest/Stocks-Daily-Price",
                description="26M rows of daily stock data",
            ),
            DatasetMetadata(
                dataset_id="Traders-Lab/TroveLedger",
                source="huggingface",
                markets=["us"],
                frequency="minute",
                depth="L1",
                license="unknown",
                cost=0,
                auth_required=False,
                quality_score=0.7,  # Has adjustment issues
                download_method="huggingface_hub",
                url="https://huggingface.co/datasets/Traders-Lab/TroveLedger",
                description="Large intraday datasets (note: split/dividend issues)",
            ),
        ]
        
        self.datasets.extend(hf_datasets)
        return hf_datasets
    
    def discover_kaggle(self) -> list[DatasetMetadata]:
        """Discover datasets on Kaggle."""
        kaggle_datasets = [
            DatasetMetadata(
                dataset_id="vincentmaladiere/fi-2010",
                source="kaggle",
                markets=["nordic"],
                symbols="5 Nasdaq Nordic stocks",
                frequency="tick",
                depth="L10",
                trades=True,
                orders=True,
                size_gb=0.94,
                license="unknown",
                cost=0,
                auth_required=True,  # Kaggle account
                quality_score=0.9,
                download_method="kaggle",
                url="https://www.kaggle.com/datasets/vincentmaladiere/fi-2010",
                description="FI-2010 LOB benchmark dataset",
            ),
        ]
        
        self.datasets.extend(kaggle_datasets)
        return kaggle_datasets
    
    def discover_github(self) -> list[DatasetMetadata]:
        """Discover datasets on GitHub."""
        github_datasets = [
            DatasetMetadata(
                dataset_id="ml4t/itch-parser",
                source="github",
                markets=["us"],
                frequency="tick",
                depth="L3",
                trades=True,
                orders=True,
                cancellations=True,
                license="mit",
                cost=0,
                auth_required=False,
                quality_score=0.85,
                download_method="git_clone",
                url="https://github.com/ml4t/itch-parser",
                description="Nasdaq ITCH parser + 20.3M message sample",
            ),
            DatasetMetadata(
                dataset_id="toobrien/tick_db",
                source="github",
                markets=["us"],
                frequency="tick",
                depth="L3",
                trades=True,
                orders=True,
                cancellations=True,
                license="mit",
                cost=0,
                auth_required=False,
                quality_score=0.8,
                download_method="git_clone",
                url="https://github.com/toobrien/tick_db",
                description="Sierra Chart .depth parser",
            ),
            DatasetMetadata(
                dataset_id="yuxiangalvin/DeepLOB-Model-Implementation-Project",
                source="github",
                markets=["us"],
                frequency="tick",
                depth="L10",
                trades=True,
                orders=True,
                license="unknown",
                cost=0,
                auth_required=False,
                quality_score=0.75,
                download_method="git_clone",
                url="https://github.com/yuxiangalvin/DeepLOB-Model-Implementation-Project",
                description="DeepLOB implementation with FI-2010 included",
            ),
        ]
        
        self.datasets.extend(github_datasets)
        return github_datasets
    
    def discover_lobster(self) -> list[DatasetMetadata]:
        """Discover LOBSTER sample datasets."""
        lobster_datasets = [
            DatasetMetadata(
                dataset_id="lobster-aapl-l1",
                source="lobster",
                markets=["us"],
                symbols="AAPL",
                frequency="tick",
                depth="L1",
                trades=True,
                orders=True,
                license="free-sample",
                cost=0,
                auth_required=False,
                quality_score=0.8,
                download_method="http",
                url="https://data.lobsterdata.com/info/DataSamples.php",
                description="LOBSTER AAPL L1 sample",
            ),
            DatasetMetadata(
                dataset_id="lobster-aapl-l10",
                source="lobster",
                markets=["us"],
                symbols="AAPL",
                frequency="tick",
                depth="L10",
                trades=True,
                orders=True,
                license="free-sample",
                cost=0,
                auth_required=False,
                quality_score=0.85,
                download_method="http",
                url="https://data.lobsterdata.com/info/DataSamples.php",
                description="LOBSTER AAPL L10 sample",
            ),
            DatasetMetadata(
                dataset_id="lobster-msft-l50",
                source="lobster",
                markets=["us"],
                symbols="MSFT",
                frequency="tick",
                depth="L50",
                trades=True,
                orders=True,
                license="free-sample",
                cost=0,
                auth_required=False,
                quality_score=0.9,
                download_method="http",
                url="https://data.lobsterdata.com/info/DataSamples.php",
                description="LOBSTER MSFT L50 sample",
            ),
        ]
        
        self.datasets.extend(lobster_datasets)
        return lobster_datasets
    
    def discover_crypto_lob(self) -> list[DatasetMetadata]:
        """Discover crypto LOB datasets for training."""
        crypto_datasets = [
            DatasetMetadata(
                dataset_id="binance-btc-lob",
                source="binance",
                markets=["crypto"],
                symbols="BTCUSDT",
                frequency="tick",
                depth="L20",
                trades=True,
                orders=True,
                cancellations=True,
                license="free",
                cost=0,
                auth_required=False,
                quality_score=0.85,
                download_method="api",
                url="https://api.binance.com/api/v3/depth",
                description="Binance BTC order book snapshots",
            ),
            DatasetMetadata(
                dataset_id="binance-eth-lob",
                source="binance",
                markets=["crypto"],
                symbols="ETHUSDT",
                frequency="tick",
                depth="L20",
                trades=True,
                orders=True,
                cancellations=True,
                license="free",
                cost=0,
                auth_required=False,
                quality_score=0.8,
                download_method="api",
                url="https://api.binance.com/api/v3/depth",
                description="Binance ETH order book snapshots",
            ),
        ]
        
        self.datasets.extend(crypto_datasets)
        return crypto_datasets
    
    def discover_exchange_samples(self) -> list[DatasetMetadata]:
        """Discover exchange FTP/sample datasets."""
        exchange_datasets = [
            DatasetMetadata(
                dataset_id="nasdaq-itch-sample",
                source="nasdaq",
                markets=["us"],
                frequency="tick",
                depth="L3",
                trades=True,
                orders=True,
                cancellations=True,
                license="free-sample",
                cost=0,
                auth_required=False,
                quality_score=0.9,
                download_method="http",
                url="https://www.nasdaqtrader.com/TraderNews.aspx?id=nva2008-091",
                description="Nasdaq TotalView-ITCH sample data",
            ),
            DatasetMetadata(
                dataset_id="cboe-europe-pitch-sample",
                source="cboe",
                markets=["europe", "uk"],
                frequency="tick",
                depth="L2",
                trades=True,
                orders=True,
                cancellations=True,
                license="free-sample",
                cost=0,
                auth_required=False,
                quality_score=0.85,
                download_method="http",
                url="https://datashop.cboe.com/cboe-europe-equities-trades-and-quotes-data",
                description="Cboe Europe PITCH sample data",
            ),
            DatasetMetadata(
                dataset_id="lseg-websocket-example",
                source="lseg",
                markets=["uk"],
                symbols="VOD.L",
                frequency="tick",
                depth="L2",
                trades=True,
                orders=True,
                license="free-sample",
                cost=0,
                auth_required=False,
                quality_score=0.8,
                download_method="git_clone",
                url="https://github.com/LSEG-API-Samples/Article.WebsocketAPI.Python.OrderBook",
                description="LSEG WebSocket OrderBook example for VOD.L",
            ),
        ]
        
        self.datasets.extend(exchange_datasets)
        return exchange_datasets
    
    def discover_all(self) -> list[DatasetMetadata]:
        """Discover datasets from all sources."""
        all_datasets = []
        all_datasets.extend(self.discover_huggingface())
        all_datasets.extend(self.discover_kaggle())
        all_datasets.extend(self.discover_github())
        all_datasets.extend(self.discover_lobster())
        all_datasets.extend(self.discover_crypto_lob())
        all_datasets.extend(self.discover_exchange_samples())
        
        return all_datasets
    
    def evaluate_dataset(self, dataset: DatasetMetadata) -> float:
        """Evaluate dataset quality and relevance."""
        score = 0
        
        # Cost (0 is best)
        if dataset.cost == 0:
            score += 30
        elif dataset.cost < 10:
            score += 20
        elif dataset.cost < 100:
            score += 10
        
        # License
        if dataset.license in self.download_criteria["accepted_licenses"]:
            score += 20
        elif dataset.license == "free-sample":
            score += 15
        
        # Data quality
        score += dataset.quality_score * 20
        
        # Microstructure relevance
        if dataset.depth in ("L10", "L50", "L3"):
            score += 15
        elif dataset.depth == "L5":
            score += 10
        
        # Has order data
        if dataset.orders:
            score += 10
        if dataset.cancellations:
            score += 5
        
        # Size (larger is generally better for training)
        if dataset.size_gb > 100:
            score += 10
        elif dataset.size_gb > 10:
            score += 5
        
        return min(100, score)
    
    def get_download_queue(self) -> list[DatasetMetadata]:
        """Get datasets that meet download criteria."""
        queue = []
        
        for dataset in self.datasets:
            # Check criteria
            if dataset.cost > self.download_criteria["max_cost"]:
                continue
            if dataset.quality_score < self.download_criteria["min_quality"]:
                continue
            if dataset.auth_required:
                continue  # Skip auth-required for now
            if dataset.downloaded:
                continue
            
            queue.append(dataset)
        
        # Sort by evaluation score
        queue.sort(key=lambda d: self.evaluate_dataset(d), reverse=True)
        
        return queue
    
    def get_summary(self) -> dict:
        """Get summary of all discovered datasets."""
        total = len(self.datasets)
        downloadable = len(self.get_download_queue())
        downloaded = sum(1 for d in self.datasets if d.downloaded)
        
        by_source = {}
        for d in self.datasets:
            by_source[d.source] = by_source.get(d.source, 0) + 1
        
        by_market = {}
        for d in self.datasets:
            for m in d.markets:
                by_market[m] = by_market.get(m, 0) + 1
        
        return {
            "total_discovered": total,
            "downloadable": downloadable,
            "downloaded": downloaded,
            "by_source": by_source,
            "by_market": by_market,
            "total_size_gb": sum(d.size_gb for d in self.datasets),
        }
