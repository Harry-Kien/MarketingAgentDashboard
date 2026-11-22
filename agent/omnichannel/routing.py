"""Phân công hội thoại với optimistic version và human-takeover fence."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from agent import db


class RoutingError(RuntimeError):
    pass


class ConversationNotFound(RoutingError):
    pass


class ConversationConflict(RoutingError):
    pass


class AssignmentDenied(RoutingError):
    pass


@dataclass(frozen=True, slots=True)
class ConversationRoutingState:
    conversation_id: UUID
    mode: str
    status: str
    assigned_to: UUID | None
    assigned_team_id: UUID | None
    version: int


class RoutingTransaction(Protocol):
    async def lock_conversation(self, conversation_id: UUID): ...

    async def can_assign(self, **kwargs) -> bool: ...

    async def apply_takeover(self, **kwargs): ...

    async def can_release(self, **kwargs) -> bool: ...

    async def can_che_do(self, **kwargs) -> bool: ...

    async def apply_che_do(self, **kwargs): ...

    async def apply_release(self, **kwargs): ...


class RoutingRepository(Protocol):
    def transaction(self): ...


def nguoi_dang_giu(conversation: Mapping[str, Any]) -> UUID | None:
    """
    Người ĐANG GIỮ hội thoại: được giao VÀ hội thoại đang ở tay người.

    `assigned_to` của hội thoại AI (`auto`/`assist`) là người bộ định tuyến
    gán theo dõi, không phải người đang nói với khách — đồng nghiệp nhận
    tiếp quản lúc khách bực là việc nên làm, không phải giành việc. Cùng định
    nghĩa với dashboard (`03-hoi-thoai.js`: "Đồng nghiệp đang giữ").
    """
    if conversation.get("mode") != "human" or not conversation.get("assigned_to"):
        return None
    return UUID(str(conversation["assigned_to"]))


def _state(row: Mapping[str, Any]) -> ConversationRoutingState:
    return ConversationRoutingState(
        conversation_id=UUID(str(row["id"])),
        mode=str(row["mode"]),
        status=str(row["status"]),
        assigned_to=UUID(str(row["assigned_to"])) if row.get("assigned_to") else None,
        assigned_team_id=(
            UUID(str(row["assigned_team_id"]))
            if row.get("assigned_team_id")
            else None
        ),
        version=int(row["version"]),
    )


class ConversationRoutingService:
    def __init__(self, repository: RoutingRepository):
        self._repository = repository

    async def takeover(
        self,
        *,
        conversation_id: UUID,
        actor_id: UUID,
        assignee_id: UUID,
        expected_version: int,
        reason: str,
        team_id: UUID | None = None,
        actor_is_admin: bool = False,
    ) -> ConversationRoutingState:
        reason = reason.strip()
        if not reason:
            raise ValueError("takeover bắt buộc có lý do")
        async with self._repository.transaction() as tx:
            conversation = await tx.lock_conversation(conversation_id)
            if conversation is None:
                raise ConversationNotFound("không tìm thấy hội thoại")
            if int(conversation["version"]) != expected_version:
                raise ConversationConflict("hội thoại đã thay đổi; tải lại trước khi nhận")
            if conversation.get("state") in {"resolved", "closed"}:
                raise ConversationConflict("hội thoại đã đóng")
            if not await tx.can_assign(
                account_id=conversation["account_id"],
                actor_id=actor_id,
                assignee_id=assignee_id,
                team_id=team_id,
                is_admin=actor_is_admin,
                current_holder_id=nguoi_dang_giu(conversation),
            ):
                raise AssignmentDenied(
                    "không có quyền giao hội thoại này: người nhận phải là thành "
                    "viên kênh (và của nhóm nếu chọn nhóm); giao cho người khác "
                    "hoặc lấy hội thoại đồng nghiệp đang giữ cần quyền quản lý kênh")
            updated = await tx.apply_takeover(
                conversation_id=conversation_id,
                account_id=conversation["account_id"],
                actor_id=actor_id,
                assignee_id=assignee_id,
                team_id=team_id,
                reason=reason,
            )
        return _state(updated)

    async def release(
        self,
        *,
        conversation_id: UUID,
        actor_id: UUID,
        expected_version: int,
        reason: str,
        actor_is_admin: bool = False,
    ) -> ConversationRoutingState:
        reason = reason.strip()
        if not reason:
            raise ValueError("release bắt buộc có lý do")
        async with self._repository.transaction() as tx:
            conversation = await tx.lock_conversation(conversation_id)
            if conversation is None:
                raise ConversationNotFound("không tìm thấy hội thoại")
            if int(conversation["version"]) != expected_version:
                raise ConversationConflict("hội thoại đã thay đổi; tải lại trước khi release")
            if conversation.get("mode") != "human":
                raise ConversationConflict("hội thoại không ở chế độ human")
            if not await tx.can_release(
                conversation=conversation,
                actor_id=actor_id,
                is_admin=actor_is_admin,
            ):
                raise AssignmentDenied("không có quyền release hội thoại")
            updated = await tx.apply_release(
                conversation_id=conversation_id,
                account_id=conversation["account_id"],
                actor_id=actor_id,
                reason=reason,
            )
        return _state(updated)


    async def dat_che_do(
        self,
        *,
        conversation_id: UUID,
        actor_id: UUID,
        che_do: str,
        expected_version: int,
        reason: str,
        actor_is_admin: bool = False,
    ) -> ConversationRoutingState:
        """
        Đổi giữa `auto` (AI gửi thẳng) và `assist` (AI soạn, người duyệt).

        VÌ SAO `human` KHÔNG ĐI QUA ĐÂY
        --------------------------------
        Chuyển sang `human` là GIAO VIỆC cho một người cụ thể — nó cần biết
        giao cho ai, kiểm quyền của người đó, và mở một bản ghi phân công.
        `takeover` đã làm đúng việc ấy. Hai đường cùng đổi một trường theo
        hai luật khác nhau là chỗ để chúng lệch nhau.

        VÌ SAO PHẢI RELEASE TRƯỚC KHI BẬT AUTO
        ---------------------------------------
        Hội thoại `human` đang có người giữ. Bật auto sau lưng họ là để AI
        nhắn chen vào giữa cuộc họ đang xử lý — khách thấy hai giọng khác
        nhau trong cùng một mạch.
        """
        reason = reason.strip()
        if not reason:
            raise ValueError("đổi chế độ bắt buộc có lý do")
        if che_do not in ("auto", "assist"):
            raise ValueError("chế độ chỉ nhận 'auto' hoặc 'assist'")

        async with self._repository.transaction() as tx:
            # Cùng fence với outbox worker: đợi job AI đang gửi kết thúc rồi
            # mới đổi, nếu không một tin soạn ở chế độ cũ lọt qua chế độ mới.
            conversation = await tx.lock_conversation(conversation_id)
            if conversation is None:
                raise ConversationNotFound("không tìm thấy hội thoại")
            if int(conversation["version"]) != expected_version:
                raise ConversationConflict(
                    "hội thoại đã thay đổi; tải lại trước khi đổi chế độ")
            if conversation.get("state") in {"resolved", "closed"}:
                raise ConversationConflict("hội thoại đã đóng")
            if conversation.get("mode") == "human":
                raise ConversationConflict(
                    "hội thoại đang có người tiếp quản — bấm "
                    "'Kết thúc tiếp quản' trước")
            # Kiểm phạm vi kênh Ở ĐÂY, không chỉ ở route: trước 16.11.2026
            # `actor_is_admin` được truyền vào rồi bỏ qua, nên nhân viên kênh
            # A bật được `auto` — AI gửi thẳng không ai duyệt — cho hội thoại
            # kênh B. NotFound chứ không Denied: cùng lý do với
            # `chan_neu_ngoai_kenh` — 403 xác nhận hội thoại tồn tại.
            if not await tx.can_che_do(
                account_id=conversation["account_id"],
                actor_id=actor_id,
                is_admin=actor_is_admin,
            ):
                raise ConversationNotFound("không tìm thấy hội thoại")
            updated = await tx.apply_che_do(
                conversation_id=conversation_id,
                account_id=conversation["account_id"],
                actor_id=actor_id,
                che_do=che_do,
                reason=reason,
            )
        return _state(updated)


class PostgresRoutingTransaction:
    def __init__(self, connection):
        self._connection = connection

    async def lock_conversation(self, conversation_id: UUID):
        # Cùng fence với outbox worker: takeover chờ provider call + finalize
        # đang chạy kết thúc, rồi hủy toàn bộ AI job chưa gửi còn lại.
        await self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"conversation-send:{conversation_id}",
        )
        return await self._connection.fetchrow(
            "SELECT * FROM conversations WHERE id = $1 FOR UPDATE",
            conversation_id,
        )

    async def can_assign(
        self,
        *,
        account_id: UUID,
        actor_id: UUID,
        assignee_id: UUID,
        team_id: UUID | None,
        is_admin: bool,
        current_holder_id: UUID | None = None,
    ) -> bool:
        if is_admin:
            assignee_ok = await self._connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM account_memberships "
                "WHERE account_id = $1 AND user_id = $2)",
                account_id,
                assignee_id,
            )
            if not assignee_ok:
                return False
            return await self._team_ok(team_id, assignee_id)
        row = await self._connection.fetchrow(
            """
            SELECT actor.role AS actor_role,
                   assignee.user_id IS NOT NULL AS assignee_ok,
                   actor.role IN ('owner', 'manager') AS quan_ly
            FROM account_memberships actor
            LEFT JOIN account_memberships assignee
              ON assignee.account_id = actor.account_id AND assignee.user_id = $3
            WHERE actor.account_id = $1 AND actor.user_id = $2
            """,
            account_id,
            actor_id,
            assignee_id,
        )
        if row is None or not row["assignee_ok"]:
            return False
        quan_ly = bool(row["quan_ly"])
        if assignee_id != actor_id and not quan_ly:
            return False
        # LẤY HỘI THOẠI ĐỒNG NGHIỆP ĐANG GIỮ cần quyền quản lý — cả khi giao
        # cho CHÍNH MÌNH. Trước 20.11.2026 vế "tự nhận" (`$2 = $3`) đủ cho
        # mọi thành viên kênh, nên nhân viên B lặng lẽ giành hội thoại A
        # đang nói dở: bản ghi phân công của A bị đóng, A không được báo, và
        # khách thấy hai người trả lời. Dashboard đã ẩn nút "Tôi tiếp quản"
        # khi đồng nghiệp đang giữ — nhưng chặn ở giao diện là chặn hỏng-mở:
        # gọi thẳng API là qua.
        if (current_holder_id is not None and current_holder_id != actor_id
                and not quan_ly):
            return False
        return await self._team_ok(team_id, assignee_id)

    async def _team_ok(self, team_id: UUID | None, assignee_id: UUID) -> bool:
        """
        Người nhận phải THUỘC nhóm được chọn.

        Trước bản này nhánh `is_admin` bỏ qua phép kiểm này — quản trị giao
        được "nhóm Kho" cho người không ở nhóm Kho, và báo cáo theo nhóm đếm
        sai mà không ai biết vì sao.
        """
        if team_id is None:
            return True
        return bool(
            await self._connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM team_members "
                "WHERE team_id = $1 AND user_id = $2)",
                team_id,
                assignee_id,
            )
        )

    async def apply_takeover(
        self,
        *,
        conversation_id: UUID,
        account_id: UUID,
        actor_id: UUID,
        assignee_id: UUID,
        team_id: UUID | None,
        reason: str,
    ):
        await self._connection.execute(
            "UPDATE conversation_assignments SET ended_at = now() "
            "WHERE conversation_id = $1 AND ended_at IS NULL",
            conversation_id,
        )
        await self._connection.execute(
            """
            INSERT INTO conversation_assignments (
                conversation_id, assigned_user_id, assigned_team_id,
                actor_id, source, reason
            ) VALUES ($1,$2,$3,$4,'takeover',$5)
            """,
            conversation_id,
            assignee_id,
            team_id,
            actor_id,
            reason,
        )
        await self._connection.execute(
            """
            WITH cancelled AS (
                UPDATE outbox_jobs job
                SET status = 'cancelled', locked_at = NULL, locked_by = NULL,
                    last_error = 'human_takeover', updated_at = now()
                FROM messages message
                WHERE job.message_id = message.id
                  AND job.conversation_id = $1
                  AND message.role = 'agent'
                  AND job.status IN ('pending', 'retry', 'processing')
                RETURNING job.message_id
            )
            UPDATE messages message
            SET delivery_status = 'cancelled', delivered = false
            WHERE message.id IN (SELECT message_id FROM cancelled)
            """,
            conversation_id,
        )
        updated = await self._connection.fetchrow(
            """
            UPDATE conversations
            SET mode = 'human', status = 'escalated', assigned_to = $2,
                assigned_team_id = $3,
                assigned_at = coalesce(assigned_at, now()),
                version = version + 1, updated_at = now()
            WHERE id = $1
            RETURNING *
            """,
            conversation_id,
            assignee_id,
            team_id,
        )
        await self._connection.execute(
            "INSERT INTO inbox_events (account_id, topic, ref_id, payload) "
            "VALUES ($1,'conversation.takeover',$2,$3)",
            account_id,
            conversation_id,
            {"assignee_id": str(assignee_id), "team_id": str(team_id) if team_id else None},
        )
        await self._connection.execute(
            "INSERT INTO events (kind, actor, ref_id, detail) "
            "VALUES ('conversation.takeover',$1,$2,$3)",
            str(actor_id),
            conversation_id,
            {"assignee_id": str(assignee_id), "reason": reason},
        )
        return updated

    async def can_release(
        self,
        *,
        conversation: Mapping[str, Any],
        actor_id: UUID,
        is_admin: bool,
    ) -> bool:
        if is_admin or conversation.get("assigned_to") == actor_id:
            return True
        return bool(
            await self._connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM account_memberships "
                "WHERE account_id = $1 AND user_id = $2 "
                "AND role IN ('owner', 'manager'))",
                conversation["account_id"],
                actor_id,
            )
        )

    async def can_che_do(
        self,
        *,
        account_id: UUID,
        actor_id: UUID,
        is_admin: bool,
    ) -> bool:
        """Người thấy mọi kênh, hoặc thành viên của tài khoản kênh này."""
        if is_admin:
            return True
        return bool(
            await self._connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM account_memberships "
                "WHERE account_id = $1 AND user_id = $2)",
                account_id,
                actor_id,
            )
        )

    async def apply_che_do(
        self,
        *,
        conversation_id: UUID,
        account_id: UUID,
        actor_id: UUID,
        che_do: str,
        reason: str,
    ):
        """
        Ghi chế độ mới.

        `status` đi theo `mode` chứ không giữ nguyên: một hội thoại từng
        `escalated` mà bật lại auto nghĩa là người đã xem và quyết cho agent
        tiếp tục. Giữ `escalated` thì nó nằm mãi trong hàng chờ người, và
        không ai biết vì sao nó vẫn ở đó.
        """
        updated = await self._connection.fetchrow(
            """
            UPDATE conversations
            SET mode = $2, status = $2,
                -- Lựa chọn của NHÂN VIÊN, khác `mode='assist'` máy tự đặt
                -- sau mỗi bản nháp — xem migration 0052.
                duyet_truoc_khi_gui = ($2 = 'assist'),
                version = version + 1, updated_at = now()
            WHERE id = $1
            RETURNING *
            """,
            conversation_id, che_do,
        )
        await self._connection.execute(
            "INSERT INTO inbox_events (account_id, topic, ref_id, payload) "
            "VALUES ($1,'conversation.che_do',$2,$3)",
            account_id, conversation_id, {"che_do": che_do, "reason": reason},
        )
        # Bật auto là cho AI gửi thẳng cho khách, KHÔNG ai duyệt. Nhật ký
        # kiểm toán phải ghi ai đã quyết và vì sao.
        await self._connection.execute(
            "INSERT INTO events (kind, actor, ref_id, detail) "
            "VALUES ('conversation.che_do',$1,$2,$3)",
            str(actor_id), conversation_id, {"che_do": che_do, "reason": reason},
        )
        return updated

    async def apply_release(
        self,
        *,
        conversation_id: UUID,
        account_id: UUID,
        actor_id: UUID,
        reason: str,
    ):
        await self._connection.execute(
            "UPDATE conversation_assignments SET ended_at = now() "
            "WHERE conversation_id = $1 AND ended_at IS NULL",
            conversation_id,
        )
        # Người kết thúc tiếp quản = việc "Khách cần người trả lời" CŨ (trước
        # mục 14.2) đã xong. Để mở là nó nằm mãi và chặn tự giải quyết — xem
        # `giai_quyet.dong_viec_tu_sinh`.
        from agent.core import thong_bao_noi_bo
        from agent.omnichannel.giai_quyet import dong_viec_tu_sinh

        await dong_viec_tu_sinh(self._connection, conversation_id)
        # Cùng lý do cho thông báo: lần chuyển giao sau phải là chuyện MỚI.
        await thong_bao_noi_bo.ket_thuc_luot_chuyen_giao(self._connection, conversation_id)
        updated = await self._connection.fetchrow(
            """
            UPDATE conversations
            SET mode = 'assist', status = 'assist', assigned_to = NULL,
                assigned_team_id = NULL, duyet_truoc_khi_gui = false,
                version = version + 1, updated_at = now()
            WHERE id = $1
            RETURNING *
            """,
            conversation_id,
        )
        await self._connection.execute(
            "INSERT INTO inbox_events (account_id, topic, ref_id, payload) "
            "VALUES ($1,'conversation.released',$2,$3)",
            account_id,
            conversation_id,
            {"reason": reason},
        )
        await self._connection.execute(
            "INSERT INTO events (kind, actor, ref_id, detail) "
            "VALUES ('conversation.released',$1,$2,$3)",
            str(actor_id),
            conversation_id,
            {"reason": reason},
        )
        return updated


class PostgresRoutingRepository:
    def __init__(self, pool_provider: Callable[[], Any] = db.pool):
        self._pool_provider = pool_provider

    @asynccontextmanager
    async def transaction(self):
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                yield PostgresRoutingTransaction(connection)
