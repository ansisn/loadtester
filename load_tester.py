#!/usr/bin/env python3
"""
HTTP负载测试工具 - 支持多代理多线程
用于测试Web服务的性能和稳定性，支持通过多个代理和多线程进行高并发测试
"""

import asyncio
import aiohttp
import time
import argparse
import statistics
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict, Optional
import json
import queue

@dataclass
class TestResult:
    """测试结果数据类"""
    status_code: int
    response_time: float
    proxy_used: str = None
    error: str = None

class LoadTester:
    def __init__(self, url: str, concurrent: int = 10, total_requests: int = 100, 
                 proxies: List[str] = None, threads: int = 1):
        self.url = url
        self.concurrent = concurrent
        self.total_requests = total_requests
        self.proxies = proxies or []
        self.threads = threads
        self.results: List[TestResult] = []
        self.start_time = 0
        self.end_time = 0
        self.results_lock = threading.Lock()
    
    def get_random_proxy(self) -> Optional[str]:
        """随机选择一个代理"""
        if not self.proxies:
            return None
        return random.choice(self.proxies)
    
    def make_sync_request(self) -> TestResult:
        """发送单个HTTP请求 - 同步版本"""
        start_time = time.time()
        proxy = self.get_random_proxy()
        proxy_url = f"http://{proxy}" if proxy else None
        
        try:
            import requests
            
            proxies_dict = {'http': proxy_url, 'https': proxy_url} if proxy_url else None
            headers = {'User-Agent': 'LoadTester/1.0'}
            
            response = requests.get(
                self.url, 
                proxies=proxies_dict,
                headers=headers,
                timeout=30
            )
            
            end_time = time.time()
            return TestResult(
                status_code=response.status_code,
                response_time=end_time - start_time,
                proxy_used=proxy
            )
        except Exception as e:
            end_time = time.time()
            return TestResult(
                status_code=0,
                response_time=end_time - start_time,
                proxy_used=proxy,
                error=str(e)
            )
    
    async def make_async_request(self, semaphore: asyncio.Semaphore) -> TestResult:
        """发送单个HTTP请求 - 异步版本"""
        async with semaphore:
            start_time = time.time()
            proxy = self.get_random_proxy()
            proxy_url = f"http://{proxy}" if proxy else None
            
            try:
                connector = aiohttp.TCPConnector(limit=100)
                timeout = aiohttp.ClientTimeout(total=30)
                
                async with aiohttp.ClientSession(
                    connector=connector, 
                    timeout=timeout
                ) as session:
                    async with session.get(
                        self.url, 
                        proxy=proxy_url,
                        headers={'User-Agent': 'LoadTester/1.0'}
                    ) as response:
                        await response.text()
                        end_time = time.time()
                        return TestResult(
                            status_code=response.status,
                            response_time=end_time - start_time,
                            proxy_used=proxy
                        )
            except Exception as e:
                end_time = time.time()
                return TestResult(
                    status_code=0,
                    response_time=end_time - start_time,
                    proxy_used=proxy,
                    error=str(e)
                )
    
    def run_thread_batch(self, requests_per_thread: int) -> List[TestResult]:
        """在单个线程中运行一批请求"""
        thread_results = []
        for _ in range(requests_per_thread):
            result = self.make_sync_request()
            thread_results.append(result)
        return thread_results
    
    async def run_async_batch(self, requests_per_thread: int) -> List[TestResult]:
        """在单个线程中异步运行一批请求"""
        semaphore = asyncio.Semaphore(self.concurrent // self.threads)
        tasks = [
            self.make_async_request(semaphore) 
            for _ in range(requests_per_thread)
        ]
        return await asyncio.gather(*tasks)
    
    def run_test(self) -> Dict:
        """运行负载测试 - 多线程版本"""
        print(f"开始负载测试...")
        print(f"目标URL: {self.url}")
        print(f"并发数: {self.concurrent}")
        print(f"线程数: {self.threads}")
        print(f"总请求数: {self.total_requests}")
        if self.proxies:
            print(f"代理数量: {len(self.proxies)}")
        print("-" * 50)
        
        self.start_time = time.time()
        
        # 计算每个线程的请求数
        requests_per_thread = self.total_requests // self.threads
        remaining_requests = self.total_requests % self.threads
        
        # 使用线程池执行请求
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = []
            
            # 为每个线程分配请求
            for i in range(self.threads):
                thread_requests = requests_per_thread
                if i < remaining_requests:
                    thread_requests += 1
                
                future = executor.submit(self.run_thread_batch, thread_requests)
                futures.append(future)
            
            # 收集所有结果
            all_results = []
            for future in as_completed(futures):
                thread_results = future.result()
                all_results.extend(thread_results)
        
        self.results = all_results
        self.end_time = time.time()
        
        return self.analyze_results()
    
    async def run_async_test(self) -> Dict:
        """运行负载测试 - 异步版本"""
        print(f"开始异步负载测试...")
        print(f"目标URL: {self.url}")
        print(f"并发数: {self.concurrent}")
        print(f"线程数: {self.threads}")
        print(f"总请求数: {self.total_requests}")
        if self.proxies:
            print(f"代理数量: {len(self.proxies)}")
        print("-" * 50)
        
        self.start_time = time.time()
        
        # 计算每个线程的请求数
        requests_per_thread = self.total_requests // self.threads
        remaining_requests = self.total_requests % self.threads
        
        # 创建线程任务
        tasks = []
        for i in range(self.threads):
            thread_requests = requests_per_thread
            if i < remaining_requests:
                thread_requests += 1
            
            task = self.run_async_batch(thread_requests)
            tasks.append(task)
        
        # 执行所有任务
        thread_results = await asyncio.gather(*tasks)
        
        # 合并结果
        all_results = []
        for results in thread_results:
            all_results.extend(results)
        
        self.results = all_results
        self.end_time = time.time()
        
        return self.analyze_results()
    
    def analyze_results(self) -> Dict:
        """分析测试结果"""
        total_time = self.end_time - self.start_time
        
        # 分离成功和失败的请求
        successful_results = [r for r in self.results if r.error is None]
        failed_results = [r for r in self.results if r.error is not None]
        
        # 响应时间统计
        response_times = [r.response_time for r in successful_results]
        
        # 状态码统计
        status_codes = {}
        for result in self.results:
            code = result.status_code
            status_codes[code] = status_codes.get(code, 0) + 1
        
        # 代理使用统计
        proxy_stats = {}
        for result in self.results:
            proxy = result.proxy_used or "直连"
            if proxy not in proxy_stats:
                proxy_stats[proxy] = {"成功": 0, "失败": 0}
            if result.error is None:
                proxy_stats[proxy]["成功"] += 1
            else:
                proxy_stats[proxy]["失败"] += 1
        
        # 计算统计数据
        stats = {
            "总请求数": self.total_requests,
            "成功请求数": len(successful_results),
            "失败请求数": len(failed_results),
            "成功率": f"{len(successful_results)/self.total_requests*100:.2f}%",
            "总耗时": f"{total_time:.2f}秒",
            "QPS": f"{self.total_requests/total_time:.2f}",
            "状态码分布": status_codes,
            "代理使用统计": proxy_stats
        }
        
        if response_times:
            stats.update({
                "平均响应时间": f"{statistics.mean(response_times)*1000:.2f}ms",
                "最小响应时间": f"{min(response_times)*1000:.2f}ms",
                "最大响应时间": f"{max(response_times)*1000:.2f}ms",
                "响应时间中位数": f"{statistics.median(response_times)*1000:.2f}ms"
            })
            
            if len(response_times) > 1:
                stats["响应时间标准差"] = f"{statistics.stdev(response_times)*1000:.2f}ms"
        
        return stats
    
    def print_results(self, stats: Dict):
        """打印测试结果"""
        print("\n" + "="*50)
        print("负载测试结果")
        print("="*50)
        
        for key, value in stats.items():
            if key == "状态码分布":
                print(f"{key}:")
                for code, count in value.items():
                    print(f"  {code}: {count}次")
            elif key == "代理使用统计":
                print(f"{key}:")
                for proxy, counts in value.items():
                    success_rate = counts["成功"] / (counts["成功"] + counts["失败"]) * 100 if (counts["成功"] + counts["失败"]) > 0 else 0
                    print(f"  {proxy}: 成功{counts['成功']}次, 失败{counts['失败']}次 (成功率: {success_rate:.1f}%)")
            else:
                print(f"{key}: {value}")
        
        print("="*50)

def load_proxies_from_file(filename: str) -> List[str]:
    """从文件加载代理列表"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            proxies = []
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    proxies.append(line)
            return proxies
    except FileNotFoundError:
        print(f"代理文件 {filename} 不存在")
        return []
    except Exception as e:
        print(f"读取代理文件时出错: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description='HTTP负载测试工具 - 支持多代理多线程')
    parser.add_argument('url', help='目标URL')
    parser.add_argument('-c', '--concurrent', type=int, default=10, help='并发数 (默认: 10)')
    parser.add_argument('-n', '--requests', type=int, default=100, help='总请求数 (默认: 100)')
    parser.add_argument('-t', '--threads', type=int, default=1, help='线程数 (默认: 1)')
    parser.add_argument('-p', '--proxy-file', help='代理列表文件路径')
    parser.add_argument('--proxy-list', nargs='+', help='直接指定代理列表')
    parser.add_argument('--async-mode', action='store_true', help='使用异步模式 (默认: 同步多线程)')
    parser.add_argument('-o', '--output', help='结果输出到JSON文件')
    
    args = parser.parse_args()
    
    # 验证URL格式
    if not args.url.startswith(('http://', 'https://')):
        args.url = 'http://' + args.url
    
    # 加载代理列表
    proxies = []
    if args.proxy_file:
        proxies = load_proxies_from_file(args.proxy_file)
    elif args.proxy_list:
        proxies = args.proxy_list
    
    # 创建测试器
    tester = LoadTester(args.url, args.concurrent, args.requests, proxies, args.threads)
    
    # 运行测试
    if args.async_mode:
        stats = asyncio.run(tester.run_async_test())
    else:
        stats = tester.run_test()
    
    # 显示结果
    tester.print_results(stats)
    
    # 保存结果到文件
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {args.output}")

if __name__ == "__main__":
    main()