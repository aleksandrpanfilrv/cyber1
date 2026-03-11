#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CyberStreet Bot v2.2.1
Production-ready VK bot for gaming club
Author: CyberStreet Team
License: Proprietary
"""

import json
import random
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

class Config:
    """Централизованная конфигурация бота"""

    # === ВАЖНО: ЗАМЕНИТЕ ЭТИ ЗНАЧЕНИЯ НА СВОИ ===
    VK_TOKEN = "vk1.a.S2d36_yK67YswWnSFYcN5kaDDHN7NrVLyOGh4mPi3vKqpQee3iEIS8SI8-IJ7aTFdpsxd9HT0InOmgiY5h_Jp0yQNaGH155oEIq0oc62phvaF_JtUvr_pMXuAXcJ8lYUbIy6Vcpmk8Kdw4uV3Ia-um23JuH3wl6b7QPqugJlE80KDguwmRC6uivUJDszHbGpq8Y8yrprmqFNa5saYqMyQg"
    GROUP_ID = 236431563
    # =============================================

    DB_PATH = Path(__file__).parent / "cyberstreet.db"

    TREASURE_ATTEMPTS_PER_PERIOD = 3
    TREASURE_PERIOD_DAYS = 14

    LOG_LEVEL = logging.INFO
    LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    PHONE_CHKALOVA = "+7 (937) 135-85-95"
    PHONE_IKRANOE = "+7 (902) 111-16-90"
    TELEGRAM_LINK = "t.me/cyberstreet30"
    VK_LINK = "vk.com/cyberstreet_30"


# ============================================================================
# МОДЕЛИ ДАННЫХ
# ============================================================================

class Branch(str, Enum):
    CHKALOVA = "chkalova"
    IKRANOE = "ikranoe"

    def __str__(self):
        return self.value

    @property
    def display_name(self) -> str:
        names = {
            Branch.CHKALOVA: "Астрахань (Чкалова)",
            Branch.IKRANOE: "Икряное"
        }
        return names[self]

    @property
    def address(self) -> str:
        addresses = {
            Branch.CHKALOVA: "ул. Чкалова 78а",
            Branch.IKRANOE: "ул. Советская 34"
        }
        return addresses[self]

    @property
    def phone(self) -> str:
        phones = {
            Branch.CHKALOVA: Config.PHONE_CHKALOVA,
            Branch.IKRANOE: Config.PHONE_IKRANOE
        }
        return phones[self]


@dataclass
class PriceConfig:
    branch: Branch
    weekday_1h: int
    weekday_3h: int
    weekday_5h: int
    weekend_1h: int
    weekend_3h: int
    weekend_5h: int

    @classmethod
    def for_branch(cls, branch: Branch) -> 'PriceConfig':
        prices = {
            Branch.CHKALOVA: cls(
                branch=branch,
                weekday_1h=90, weekday_3h=240, weekday_5h=350,
                weekend_1h=100, weekend_3h=270, weekend_5h=370
            ),
            Branch.IKRANOE: cls(
                branch=branch,
                weekday_1h=100, weekday_3h=270, weekday_5h=370,
                weekend_1h=110, weekend_3h=290, weekend_5h=400
            )
        }
        return prices[branch]


@dataclass
class PlayStationPrices:
    per_hour: int = 250
    three_hours: int = 600
    night: int = 1500

    @property
    def night_period(self) -> str:
        return "22:00 - 08:00"


@dataclass
class ComputerSpec:
    zone: str
    count: int
    cpu: str
    gpu: str
    ram: Optional[str] = None
    monitor: Optional[str] = None
    keyboard: Optional[str] = None
    mouse: Optional[str] = None
    headset: Optional[str] = None


class PCSpecs:
    CHKALOVA = [
        ComputerSpec(
            zone="Общий зал", count=15,
            cpu="Intel i5-12400F",
            gpu="MSI RTX 3060 / AMD RADEON RX6600",
            monitor="AOC 24\" 165Hz",
            keyboard="Ardor gaming blade",
            mouse="Logitech G102",
            headset="HyperX Stinger 2"
        ),
        ComputerSpec(
            zone="BOOTCAMP", count=5,
            cpu="Intel i5-13400F",
            gpu="NVIDIA RTX 3060 Ti",
            monitor="AOC 25\" 240Hz",
            keyboard="Dark Project 5075 (механическая)",
            mouse="Logitech G102",
            headset="HAVIT H2008D"
        )
    ]

    IKRANOE = [
        ComputerSpec(
            zone="Общий зал", count=17,
            cpu="Intel i5-12400F",
            gpu="GeForce RTX 5060",
            ram="DDR5 16GB",
            monitor="AOC 24\" 180Hz",
            keyboard="Redragon",
            mouse="Logitech G102",
            headset="HyperX Stinger 2"
        ),
        ComputerSpec(
            zone="VIP зал", count=5,
            cpu="Intel i5-13400F",
            gpu="GeForce RTX 5060",
            ram="DDR4 32GB",
            monitor="AOC 27\" 240Hz",
            keyboard="Механическая",
            mouse="Logitech G102",
            headset="HyperX Stinger 2"
        )
    ]

    @classmethod
    def for_branch(cls, branch: Branch) -> List[ComputerSpec]:
        return cls.CHKALOVA if branch == Branch.CHKALOVA else cls.IKRANOE


@dataclass
class TreasurePrize:
    id: str
    name: str
    description: str
    chance: float
    emoji: str = "🎁"

    def format_message(self) -> str:
        return f"{self.emoji} {self.name}\n{self.description}"


class TreasurePrizes:
    _PRIZES = [
        TreasurePrize(
            id="miss",
            name="Мимо!",
            description="Здесь нет сокровищ... Попробуй в другой раз!",
            chance=0.60, emoji="😢"
        ),
        TreasurePrize(
            id="cashback_30_small",
            name="КЭШБЭК 30%",
            description="Закидываешь 100₽ → получаешь 130₽ на счёт! 🎉",
            chance=0.25, emoji="💰"
        ),
        TreasurePrize(
            id="cashback_50",
            name="Кэшбек 50%",
            description="Пополняй счёт и получай +50% сверху! 💎",
            chance=0.10, emoji="💎"
        ),
        TreasurePrize(
            id="cashback_30_big",
            name="КЭШБЭК 30% (БОЛЬШОЙ)",
            description="Закидываешь 300₽ → получаешь 390₽ на счёт! 🏆",
            chance=0.05, emoji="🏆"
        )
    ]

    @classmethod
    def get_random(cls) -> TreasurePrize:
        r = random.random()
        cumulative = 0.0
        for prize in cls._PRIZES:
            cumulative += prize.chance
            if r < cumulative:
                return prize
        return cls._PRIZES[-1]


class Games:
    LIST = [
        "DOTA 2", "CS2", "PUBG", "Apex Legends",
        "GTA 5", "World of Tanks", "VALORANT", "FORTNITE"
    ]

    @classmethod
    def format_list(cls) -> str:
        return " • ".join(cls.LIST)


# ============================================================================
# РАБОТА С БАЗОЙ ДАННЫХ (ИСПРАВЛЕНО)
# ============================================================================

class Database:
    _instance: Optional['Database'] = None
    _connection: Optional[sqlite3.Connection] = None

    def __new__(cls) -> 'Database':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        # ===== ИСПРАВЛЕНИЕ: убран detect_types =====
        self._connection = sqlite3.connect(
            str(Config.DB_PATH),
            check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        with self._connection:
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS treasure_period (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                )
            """)

            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    vk_id INTEGER PRIMARY KEY,
                    selected_branch TEXT NOT NULL DEFAULT 'chkalova',
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    last_seen TEXT DEFAULT (datetime('now','localtime'))
                )
            """)

            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS treasure_opens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vk_id INTEGER NOT NULL,
                    prize_id TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    opened_at TEXT DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (vk_id) REFERENCES users (vk_id)
                )
            """)

            self._connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_treasure_opens_period
                ON treasure_opens(vk_id, period_start)
            """)

            self._ensure_period_exists()

    def _ensure_period_exists(self) -> None:
        cursor = self._connection.execute("SELECT COUNT(*) FROM treasure_period")
        if cursor.fetchone()[0] == 0:
            self._create_new_period()

    def _create_new_period(self) -> Tuple[datetime, datetime]:
        now = datetime.now()
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=Config.TREASURE_PERIOD_DAYS)

        with self._connection:
            self._connection.execute("""
                INSERT OR REPLACE INTO treasure_period (id, period_start, period_end)
                VALUES (1, ?, ?)
            """, (period_start.isoformat(), period_end.isoformat()))

        return period_start, period_end

    @staticmethod
    def _to_datetime(value) -> Optional[datetime]:
        """Безопасная конвертация значения из БД в datetime"""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return None

    def get_current_period(self) -> Tuple[datetime, datetime]:
        cursor = self._connection.execute("""
            SELECT period_start, period_end FROM treasure_period WHERE id = 1
        """)
        row = cursor.fetchone()

        if not row:
            return self._create_new_period()

        period_start = self._to_datetime(row['period_start'])
        period_end = self._to_datetime(row['period_end'])

        if period_start is None or period_end is None:
            return self._create_new_period()

        now = datetime.now()
        if now > period_end:
            return self._create_new_period()

        return period_start, period_end

    def get_period_info(self) -> Dict[str, Any]:
        period_start, period_end = self.get_current_period()
        now = datetime.now()
        delta = period_end - now
        days_left = delta.days
        hours_left = delta.seconds // 3600

        return {
            'start': period_start,
            'end': period_end,
            'days_left': max(0, days_left),
            'hours_left': max(0, hours_left),
            'is_active': now <= period_end
        }

    def get_or_create_user(self, vk_id: int) -> sqlite3.Row:
        with self._connection:
            cursor = self._connection.execute(
                "SELECT * FROM users WHERE vk_id = ?", (vk_id,)
            )
            user = cursor.fetchone()

            if user is None:
                self._connection.execute(
                    "INSERT INTO users (vk_id) VALUES (?)", (vk_id,)
                )
                cursor = self._connection.execute(
                    "SELECT * FROM users WHERE vk_id = ?", (vk_id,)
                )
                user = cursor.fetchone()
            else:
                self._connection.execute(
                    "UPDATE users SET last_seen = datetime('now','localtime') WHERE vk_id = ?",
                    (vk_id,)
                )
            return user

    def update_user_branch(self, vk_id: int, branch: Branch) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE users SET selected_branch = ? WHERE vk_id = ?",
                (branch.value, vk_id)
            )

    def get_period_opens(self, vk_id: int) -> int:
        period_start, _ = self.get_current_period()
        with self._connection:
            cursor = self._connection.execute("""
                SELECT COUNT(*) FROM treasure_opens
                WHERE vk_id = ? AND period_start = ?
            """, (vk_id, period_start.isoformat()))
            return cursor.fetchone()[0]

    def add_treasure_open(self, vk_id: int, prize_id: str) -> None:
        period_start, _ = self.get_current_period()
        with self._connection:
            self._connection.execute("""
                INSERT INTO treasure_opens (vk_id, prize_id, period_start)
                VALUES (?, ?, ?)
            """, (vk_id, prize_id, period_start.isoformat()))

    def get_user_stats(self, vk_id: int) -> Dict[str, int]:
        with self._connection:
            cursor = self._connection.execute("""
                SELECT
                    COUNT(*) as total_opens,
                    SUM(CASE WHEN prize_id != 'miss' THEN 1 ELSE 0 END) as total_prizes
                FROM treasure_opens WHERE vk_id = ?
            """, (vk_id,))
            row = cursor.fetchone()
            if row and row['total_opens']:
                return {
                    'total_opens': row['total_opens'],
                    'total_prizes': row['total_prizes'] or 0
                }
            return {'total_opens': 0, 'total_prizes': 0}

    def get_all_users_count(self) -> int:
        with self._connection:
            cursor = self._connection.execute("SELECT COUNT(*) FROM users")
            return cursor.fetchone()[0]

    def get_period_stats(self) -> Dict[str, Any]:
        period_start, period_end = self.get_current_period()
        with self._connection:
            cursor = self._connection.execute("""
                SELECT
                    COUNT(*) as total_opens,
                    COUNT(DISTINCT vk_id) as unique_users,
                    SUM(CASE WHEN prize_id != 'miss' THEN 1 ELSE 0 END) as total_prizes
                FROM treasure_opens WHERE period_start = ?
            """, (period_start.isoformat(),))
            row = cursor.fetchone()
            return {
                'total_opens': row['total_opens'] if row else 0,
                'unique_users': row['unique_users'] if row else 0,
                'total_prizes': row['total_prizes'] or 0 if row else 0,
                'period_start': period_start,
                'period_end': period_end
            }


# ============================================================================
# ФОРМАТТЕРЫ СООБЩЕНИЙ
# ============================================================================

class MessageFormatter:
    BOX = {
        'tl': '╔', 'tr': '╗', 'bl': '╚', 'br': '╝',
        'h': '═', 'v': '║', 'hl': '╠', 'hr': '╣',
    }

    @classmethod
    def _box_line(cls, text: str, width: int = 40, align: str = 'left') -> str:
        text = text[:width - 4]
        if align == 'center':
            return f"{cls.BOX['v']} {text:^{width - 3}} {cls.BOX['v']}"
        return f"{cls.BOX['v']} {text:<{width - 3}} {cls.BOX['v']}"

    @classmethod
    def _box_header(cls, text: str, width: int = 40) -> str:
        return (
            f"{cls.BOX['tl']}{cls.BOX['h'] * (width - 2)}{cls.BOX['tr']}\n"
            + cls._box_line(text, width, 'center') + "\n"
            + f"{cls.BOX['hl']}{cls.BOX['h'] * (width - 2)}{cls.BOX['hr']}"
        )

    @classmethod
    def _box_footer(cls, width: int = 40) -> str:
        return f"{cls.BOX['bl']}{cls.BOX['h'] * (width - 2)}{cls.BOX['br']}"

    @classmethod
    def price_list(cls, branch: Branch) -> str:
        prices = PriceConfig.for_branch(branch)
        w = 44
        lines = [
            cls._box_header(f"🎮 CYBERSTREET | {branch.display_name}", w),
            cls._box_line(f"📍 {branch.address}", w),
            cls._box_line("", w),
            cls._box_line("💻 АРЕНДА ПК", w, 'center'),
            cls._box_line("", w),
            cls._box_line("Будние дни:", w),
            cls._box_line(f"  1 час: {prices.weekday_1h}₽", w),
            cls._box_line(f"  3 часа: {prices.weekday_3h}₽", w),
            cls._box_line(f"  5 часов: {prices.weekday_5h}₽", w),
            cls._box_line("", w),
            cls._box_line("Выходные (ПТ-ВС):", w),
            cls._box_line(f"  1 час: {prices.weekend_1h}₽", w),
            cls._box_line(f"  3 часа: {prices.weekend_3h}₽", w),
            cls._box_line(f"  5 часов: {prices.weekend_5h}₽", w),
        ]

        if branch == Branch.IKRANOE:
            ps = PlayStationPrices()
            lines.extend([
                cls._box_line("", w),
                cls._box_line("🎯 PLAYSTATION", w, 'center'),
                cls._box_line("", w),
                cls._box_line(f"  1 час: {ps.per_hour}₽", w),
                cls._box_line(f"  3 часа: {ps.three_hours}₽", w),
                cls._box_line(f"  Ночь ({ps.night_period}): {ps.night}₽", w),
            ])

        lines.append(cls._box_footer(w))
        return "\n".join(lines)

    @classmethod
    def pc_specs(cls, branch: Branch) -> str:
        specs = PCSpecs.for_branch(branch)
        w = 44
        lines = [
            cls._box_header(f"🖥 ПК | {branch.display_name}", w),
        ]

        for spec in specs:
            lines.append(cls._box_line("", w))
            lines.append(cls._box_line(f"🔹 {spec.zone} ({spec.count} шт.)", w))
            lines.append(cls._box_line(f"  CPU: {spec.cpu}", w))
            lines.append(cls._box_line(f"  GPU: {spec.gpu}", w))
            if spec.ram:
                lines.append(cls._box_line(f"  RAM: {spec.ram}", w))
            if spec.monitor:
                lines.append(cls._box_line(f"  Монитор: {spec.monitor}", w))
            if spec.keyboard:
                lines.append(cls._box_line(f"  Клавиатура: {spec.keyboard}", w))
            if spec.mouse:
                lines.append(cls._box_line(f"  Мышь: {spec.mouse}", w))
            if spec.headset:
                lines.append(cls._box_line(f"  Наушники: {spec.headset}", w))

        lines.append(cls._box_footer(w))
        return "\n".join(lines)

    @classmethod
    def welcome(cls) -> str:
        return (
            "🎮 Добро пожаловать в CyberStreet!\n\n"
            "Мы — сеть игровых клубов в Астрахани и Икряном.\n\n"
            "🕹 Мощные ПК, крутая атмосфера,\n"
            "турниры и акции!\n\n"
            "Выбери филиал, чтобы начать 👇"
        )

    @classmethod
    def branch_info(cls, branch: Branch) -> str:
        specs = PCSpecs.for_branch(branch)
        total_pcs = sum(s.count for s in specs)
        return (
            f"📍 {branch.display_name}\n"
            f"🏠 Адрес: {branch.address}\n"
            f"📞 Телефон: {branch.phone}\n"
            f"🖥 Всего ПК: {total_pcs}\n\n"
            f"Выберите, что вас интересует 👇"
        )

    @classmethod
    def contacts(cls) -> str:
        return (
            "📞 КОНТАКТЫ CYBERSTREET\n\n"
            f"🏠 Астрахань (Чкалова 78а):\n"
            f"   📱 {Config.PHONE_CHKALOVA}\n\n"
            f"🏠 Икряное (Советская 34):\n"
            f"   📱 {Config.PHONE_IKRANOE}\n\n"
            f"💬 Telegram: {Config.TELEGRAM_LINK}\n"
            f"💙 VK: {Config.VK_LINK}\n\n"
            "Ждём вас! 🎮"
        )

    @classmethod
    def games_list(cls) -> str:
        return (
            "🎮 УСТАНОВЛЕННЫЕ ИГРЫ\n\n"
            + "\n".join(f"  • {g}" for g in Games.LIST)
            + "\n\n...и ещё 100+ игр!\n"
            "Если нужной игры нет — установим по запросу! 😉"
        )

    @classmethod
    def treasure_result(cls, prize: TreasurePrize, opens_left: int,
                        period_info: Dict) -> str:
        msg = (
            "🏴‍☠️ СУНДУК С СОКРОВИЩАМИ\n\n"
            f"{prize.format_message()}\n\n"
            f"Осталось попыток: {opens_left}\n"
        )
        if opens_left > 0:
            msg += "Попробуй ещё! 👇"
        else:
            days = period_info['days_left']
            msg += f"Новые попытки через {days} дн."
        return msg

    @classmethod
    def treasure_info(cls, opens_left: int, period_info: Dict) -> str:
        return (
            "🏴‍☠️ СУНДУК С СОКРОВИЩАМИ\n\n"
            "Открой сундук и получи приз!\n\n"
            "Возможные призы:\n"
            "  💰 Кэшбэк 30% (100₽ → 130₽)\n"
            "  💎 Кэшбэк 50%\n"
            "  🏆 Кэшбэк 30% (300₽ → 390₽)\n\n"
            f"Попыток осталось: {opens_left} из {Config.TREASURE_ATTEMPTS_PER_PERIOD}\n"
            f"До обновления: {period_info['days_left']} дн.\n\n"
            "Нажми «Открыть сундук» 👇"
        )

    @classmethod
    def no_attempts(cls, period_info: Dict) -> str:
        return (
            "🏴‍☠️ СУНДУК С СОКРОВИЩАМИ\n\n"
            "❌ Попытки закончились!\n\n"
            f"Новые попытки будут через {period_info['days_left']} дн. "
            f"{period_info['hours_left']} ч.\n\n"
            "А пока — приходи поиграть! 🎮"
        )


# ============================================================================
# КЛАВИАТУРЫ
# ============================================================================

class Keyboards:
    """Все клавиатуры бота"""

    @staticmethod
    def main_menu() -> str:
        kb = VkKeyboard(one_time=False)
        kb.add_button("🏠 Филиалы", color=VkKeyboardColor.PRIMARY)
        kb.add_button("💰 Цены", color=VkKeyboardColor.PRIMARY)
        kb.add_line()
        kb.add_button("🖥 Компьютеры", color=VkKeyboardColor.SECONDARY)
        kb.add_button("🎮 Игры", color=VkKeyboardColor.SECONDARY)
        kb.add_line()
        kb.add_button("🏴‍☠️ Сундук сокровищ", color=VkKeyboardColor.POSITIVE)
        kb.add_line()
        kb.add_button("📞 Контакты", color=VkKeyboardColor.SECONDARY)
        return kb.get_keyboard()

    @staticmethod
    def branch_select() -> str:
        kb = VkKeyboard(one_time=False)
        kb.add_button("📍 Астрахань (Чкалова)", color=VkKeyboardColor.PRIMARY)
        kb.add_line()
        kb.add_button("📍 Икряное", color=VkKeyboardColor.PRIMARY)
        kb.add_line()
        kb.add_button("◀ Назад", color=VkKeyboardColor.SECONDARY)
        return kb.get_keyboard()

    @staticmethod
    def branch_menu(branch: Branch) -> str:
        kb = VkKeyboard(one_time=False)
        kb.add_button("💰 Цены", color=VkKeyboardColor.PRIMARY)
        kb.add_button("🖥 Компьютеры", color=VkKeyboardColor.PRIMARY)
        kb.add_line()
        kb.add_button("🎮 Игры", color=VkKeyboardColor.SECONDARY)
        kb.add_button("📞 Контакты", color=VkKeyboardColor.SECONDARY)
        kb.add_line()
        kb.add_button("🏴‍☠️ Сундук сокровищ", color=VkKeyboardColor.POSITIVE)
        kb.add_line()
        kb.add_button("◀ Назад", color=VkKeyboardColor.SECONDARY)
        return kb.get_keyboard()

    @staticmethod
    def treasure(can_open: bool = True) -> str:
        kb = VkKeyboard(one_time=False)
        if can_open:
            kb.add_button("🔓 Открыть сундук", color=VkKeyboardColor.POSITIVE)
            kb.add_line()
        kb.add_button("◀ Назад", color=VkKeyboardColor.SECONDARY)
        return kb.get_keyboard()

    @staticmethod
    def after_treasure(can_open: bool) -> str:
        kb = VkKeyboard(one_time=False)
        if can_open:
            kb.add_button("🔓 Открыть ещё раз", color=VkKeyboardColor.POSITIVE)
            kb.add_line()
        kb.add_button("◀ Назад в меню", color=VkKeyboardColor.PRIMARY)
        return kb.get_keyboard()


# ============================================================================
# ОСНОВНОЙ КЛАСС БОТА
# ============================================================================

class CyberStreetBot:
    """Главный класс бота"""

    def __init__(self):
        self.logger = logging.getLogger("main")
        self.logger.info("Инициализация бота CyberStreet...")

        # VK API
        self.vk_session = vk_api.VkApi(token=Config.VK_TOKEN)
        self.vk = self.vk_session.get_api()
        self.longpoll = VkBotLongPoll(self.vk_session, Config.GROUP_ID)

        # База данных
        self.db = Database()

        # Состояния пользователей {vk_id: state_string}
        self.user_states: Dict[int, str] = {}
        # Выбранный филиал {vk_id: Branch}
        self.user_branches: Dict[int, Branch] = {}

        self.logger.info(f"✓ Бот настроен для группы {Config.GROUP_ID}")
        self.logger.info(f"✓ Период сокровищ: {Config.TREASURE_PERIOD_DAYS} дней")
        self.logger.info(f"✓ Попыток за период: {Config.TREASURE_ATTEMPTS_PER_PERIOD}")

    def send(self, peer_id: int, message: str,
             keyboard: Optional[str] = None) -> None:
        """Отправка сообщения пользователю"""
        try:
            params: Dict[str, Any] = {
                'peer_id': peer_id,
                'message': message,
                'random_id': get_random_id(),
            }
            if keyboard:
                params['keyboard'] = keyboard
            self.vk.messages.send(**params)
        except Exception as e:
            self.logger.error(f"Ошибка отправки сообщения {peer_id}: {e}")

    # ---- Получение филиала пользователя ----

    def _get_branch(self, vk_id: int) -> Branch:
        """Возвращает выбранный филиал (по умолчанию Чкалова)"""
        if vk_id in self.user_branches:
            return self.user_branches[vk_id]
        user = self.db.get_or_create_user(vk_id)
        try:
            branch = Branch(user['selected_branch'])
        except (ValueError, KeyError):
            branch = Branch.CHKALOVA
        self.user_branches[vk_id] = branch
        return branch

    def _set_branch(self, vk_id: int, branch: Branch) -> None:
        self.user_branches[vk_id] = branch
        self.db.update_user_branch(vk_id, branch)

    # ---- Обработчики команд ----

    def _handle_start(self, vk_id: int) -> None:
        self.db.get_or_create_user(vk_id)
        self.user_states[vk_id] = "main_menu"
        self.send(vk_id, MessageFormatter.welcome(), Keyboards.main_menu())

    def _handle_branches(self, vk_id: int) -> None:
        self.user_states[vk_id] = "branch_select"
        self.send(vk_id, "Выберите филиал 👇", Keyboards.branch_select())

    def _handle_branch_selected(self, vk_id: int, branch: Branch) -> None:
        self._set_branch(vk_id, branch)
        self.user_states[vk_id] = "branch_menu"
        self.send(
            vk_id,
            MessageFormatter.branch_info(branch),
            Keyboards.branch_menu(branch)
        )

    def _handle_prices(self, vk_id: int) -> None:
        branch = self._get_branch(vk_id)
        self.send(
            vk_id,
            MessageFormatter.price_list(branch),
            Keyboards.branch_menu(branch)
        )

    def _handle_specs(self, vk_id: int) -> None:
        branch = self._get_branch(vk_id)
        self.send(
            vk_id,
            MessageFormatter.pc_specs(branch),
            Keyboards.branch_menu(branch)
        )

    def _handle_games(self, vk_id: int) -> None:
        self.send(vk_id, MessageFormatter.games_list(), Keyboards.main_menu())

    def _handle_contacts(self, vk_id: int) -> None:
        self.send(vk_id, MessageFormatter.contacts(), Keyboards.main_menu())

    def _handle_treasure_menu(self, vk_id: int) -> None:
        self.db.get_or_create_user(vk_id)
        opens = self.db.get_period_opens(vk_id)
        left = max(0, Config.TREASURE_ATTEMPTS_PER_PERIOD - opens)
        period_info = self.db.get_period_info()

        if left > 0:
            self.send(
                vk_id,
                MessageFormatter.treasure_info(left, period_info),
                Keyboards.treasure(can_open=True)
            )
        else:
            self.send(
                vk_id,
                MessageFormatter.no_attempts(period_info),
                Keyboards.treasure(can_open=False)
            )
        self.user_states[vk_id] = "treasure"

    def _handle_treasure_open(self, vk_id: int) -> None:
        self.db.get_or_create_user(vk_id)
        opens = self.db.get_period_opens(vk_id)
        left = Config.TREASURE_ATTEMPTS_PER_PERIOD - opens
        period_info = self.db.get_period_info()

        if left <= 0:
            self.send(
                vk_id,
                MessageFormatter.no_attempts(period_info),
                Keyboards.treasure(can_open=False)
            )
            return

        # Розыгрыш приза
        prize = TreasurePrizes.get_random()
        self.db.add_treasure_open(vk_id, prize.id)
        left -= 1

        self.logger.info(
            f"Пользователь {vk_id} открыл сундук: {prize.id} "
            f"(осталось {left})"
        )

        self.send(
            vk_id,
            MessageFormatter.treasure_result(prize, left, period_info),
            Keyboards.after_treasure(can_open=left > 0)
        )

    def _handle_back(self, vk_id: int) -> None:
        state = self.user_states.get(vk_id, "main_menu")
        if state == "branch_menu":
            self._handle_branches(vk_id)
        else:
            self._handle_start(vk_id)

    # ---- Роутер сообщений ----

    def _route_message(self, vk_id: int, text: str) -> None:
        """Маршрутизация входящего сообщения"""
        text_lower = text.lower().strip()

        # Команды, которые работают из любого состояния
        if text_lower in ("начать", "start", "привет", "здравствуйте"):
            self._handle_start(vk_id)
            return

        if "филиал" in text_lower or text_lower == "🏠 филиалы":
            self._handle_branches(vk_id)
            return

        if "астрахан" in text_lower or "чкалов" in text_lower:
            self._handle_branch_selected(vk_id, Branch.CHKALOVA)
            return

        if "икрян" in text_lower:
            self._handle_branch_selected(vk_id, Branch.IKRANOE)
            return

        if "цен" in text_lower or text_lower == "💰 цены":
            self._handle_prices(vk_id)
            return

        if "компьютер" in text_lower or "пк" in text_lower or text_lower == "🖥 компьютеры":
            self._handle_specs(vk_id)
            return

        if "игр" in text_lower or text_lower == "🎮 игры":
            self._handle_games(vk_id)
            return

        if "контакт" in text_lower or "телефон" in text_lower or text_lower == "📞 контакты":
            self._handle_contacts(vk_id)
            return

        if "сундук" in text_lower or "сокровищ" in text_lower:
            self._handle_treasure_menu(vk_id)
            return

        if "открыть" in text_lower:
            self._handle_treasure_open(vk_id)
            return

        if text_lower in ("◀ назад", "назад", "◀ назад в меню"):
            self._handle_back(vk_id)
            return

        # Неизвестная команда — показываем главное меню
        self.send(
            vk_id,
            "🤔 Не понял тебя. Вот главное меню 👇",
            Keyboards.main_menu()
        )
        self.user_states[vk_id] = "main_menu"

    # ---- Запуск ----

    def run(self) -> None:
        """Основной цикл бота"""
        # Проверяем период при старте
        period_info = self.db.get_period_info()
        self.logger.info(
            f"📅 Текущий период сокровищ: "
            f"{period_info['start'].strftime('%d.%m.%Y')} — "
            f"{period_info['end'].strftime('%d.%m.%Y')} "
            f"(осталось {period_info['days_left']} дн.)"
        )

        self.logger.info("🚀 Бот запущен и ожидает сообщения...")

        while True:
            try:
                for event in self.longpoll.listen():
                    if event.type == VkBotEventType.MESSAGE_NEW:
                        msg = event.obj.message
                        vk_id = msg['peer_id']
                        text = msg.get('text', '')

                        if text:
                            self.logger.info(
                                f"📩 [{vk_id}]: {text[:80]}"
                            )
                            self._route_message(vk_id, text)

            except KeyboardInterrupt:
                self.logger.info("⏹ Бот остановлен вручную")
                break
            except Exception as e:
                self.logger.error(f"⚠ Ошибка в цикле: {e}", exc_info=True)
                time.sleep(3)  # Пауза перед переподключением


# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=Config.LOG_LEVEL,
        format=Config.LOG_FORMAT,
        datefmt=Config.LOG_DATE_FORMAT,
    )

    try:
        bot = CyberStreetBot()
        bot.run()
    except Exception as e:
        logging.error(f"💥 Фатальная ошибка: {e}", exc_info=True)
        raise