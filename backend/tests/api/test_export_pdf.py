"""Integration tests для PDF экспорта (5.3).

Покрывает:
- Service: generate_project_pdf → bytes + valid %PDF header + кириллица
- Endpoint: GET /api/projects/{id}/export/pdf → 200 + MIME + RFC5987
  filename + 404 / 401

Текстовое содержимое PDF не парсим (WeasyPrint embed'ит шрифты, text
extraction требует pypdf с dict cmap). Вместо этого полагаемся на
факт что HTML template рендерится в bytes и signature валидна —
более глубокая проверка происходит в service-level через рендер
HTML и Jinja2 (тест `test_html_contains_content_fields`).
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.export.excel_exporter import ProjectNotFoundForExport
from app.export.pdf_exporter import generate_project_pdf
from app.export.pdf_sections import ALL_SECTIONS
from tests.api.test_calculation import _seed_minimal_project


PDF_MIME = "application/pdf"


# ============================================================
# Service-level tests
# ============================================================


class TestGenerateProjectPdf:
    async def test_returns_valid_pdf_bytes(self, db_session: AsyncSession):
        project_id, _, _, _ = await _seed_minimal_project(db_session)
        result = await generate_project_pdf(db_session, project_id)

        assert isinstance(result, bytes)
        assert len(result) > 0
        # PDF файл всегда начинается с %PDF- (ASCII)
        assert result[:5] == b"%PDF-"

    async def test_size_under_5_mb(self, db_session: AsyncSession):
        """Критерий готовности: PDF меньше 5 MB для типичного проекта."""
        project_id, _, _, _ = await _seed_minimal_project(db_session)
        result = await generate_project_pdf(db_session, project_id)
        assert len(result) < 5 * 1024 * 1024

    async def test_handles_cyrillic_project_name(
        self, db_session: AsyncSession
    ):
        """Кириллица в названии проекта не ломает рендер.

        WeasyPrint + fonts-dejavu в Dockerfile — DejaVu Sans поддерживает
        кириллицу. Без этого пакета кириллические символы отрендерились
        бы как пустые квадраты (и тест упал бы визуально, но не по
        экспепшену).
        """
        from app.models import Project

        project_id, _, _, _ = await _seed_minimal_project(db_session)
        project = await db_session.get(Project, project_id)
        assert project is not None
        project.name = "Проект на русском с кириллицей"
        project.description = "Описание с ёё и ё"
        await db_session.flush()

        result = await generate_project_pdf(db_session, project_id)
        assert result[:5] == b"%PDF-"
        assert len(result) > 0

    async def test_handles_full_content_fields(
        self, db_session: AsyncSession
    ):
        """Проект со всеми content полями из Phase 4.5 → рендер ок."""
        from datetime import date as _date

        from app.models import Project

        project_id, _, _, _ = await _seed_minimal_project(db_session)
        project = await db_session.get(Project, project_id)
        assert project is not None
        project.description = "Описание проекта"
        project.gate_stage = "G3"
        project.passport_date = _date(2025, 9, 1)
        project.project_owner = "CEO"
        project.risks = ["Конкуренты", "Регулятор"]
        project.function_readiness = {
            "R&D": {"status": "green", "notes": "готово"},
            "Marketing": {"status": "yellow", "notes": "в работе"},
            "Sales": {"status": "red", "notes": "риск"},
        }
        project.roadmap_tasks = [
            {
                "name": "Задача 1",
                "start_date": "2025-04-01",
                "end_date": "2025-05-01",
                "status": "in_progress",
                "owner": "Owner",
            }
        ]
        project.approvers = [
            {"metric": "NPV", "name": "CFO", "source": "модель"}
        ]
        project.validation_tests = {
            "concept_test": {"score": 85, "notes": "отлично"},
            "naming": {"score": 70, "notes": "ок"},
        }
        project.executive_summary = "Проект окупится за 4 года."
        await db_session.flush()

        result = await generate_project_pdf(db_session, project_id)
        assert result[:5] == b"%PDF-"
        # С content полями PDF должен быть не сильно меньше минимального
        # (значит секции реально заполнены, а не пропущены)
        assert len(result) > 20_000

    async def test_html_template_renders_content_fields(
        self, db_session: AsyncSession
    ):
        """Service-level assertion что Jinja2 выкинет нужный текст в HTML.

        Проверяем на уровне HTML рендера (до WeasyPrint), потому что
        парсинг PDF для assertion текстового содержимого хрупкий.
        Jinja2 рендер — единственный источник правды для текста.
        """
        from app.export.pdf_exporter import _jinja_env
        from app.models import Project

        project_id, _, _, _ = await _seed_minimal_project(db_session)
        project = await db_session.get(Project, project_id)
        assert project is not None
        project.description = "МАРКЕР_DESCRIPTION_123"
        project.risks = ["МАРКЕР_РИСК_ABC"]
        project.roadmap_tasks = [
            {"name": "МАРКЕР_ЗАДАЧА_XYZ", "status": "in_progress"}
        ]
        await db_session.flush()

        # Запрашиваем PDF — побочный эффект: template рендерится
        await generate_project_pdf(db_session, project_id)

        # Прямой рендер template с минимальным контекстом для проверки
        # наличия маркеров (если template был бы сломан, это дало бы
        # Jinja2 exception)
        template = _jinja_env.get_template("project_passport.html")
        from app.export.pdf_exporter import (
            _build_pnl_context,
            _build_risks_list,
            _build_roadmap_rows,
            _fmt_money,
            _fmt_pct,
            _gate_label,
            VALIDATION_SUBTESTS,
        )

        pnl_ctx = _build_pnl_context(None)
        html_str = template.render(
            active_sections=set(ALL_SECTIONS),
            project=project,
            inflation_profile_name="—",
            validation_subtests=VALIDATION_SUBTESTS,
            sku_rows=[],
            package_images=[],
            kpi_rows=[],
            per_unit_kpi=[],
            pnl_years=pnl_ctx["pnl_years"],
            pnl_rows=pnl_ctx["pnl_rows"],
            bom_top=[],
            fin_plan_rows=[],
            risks_list=_build_risks_list(project),
            function_rows=[],
            roadmap_rows=_build_roadmap_rows(project),
            approver_rows=[],
            gate_label=_gate_label,
            fmt_money=_fmt_money,
            fmt_pct=_fmt_pct,
            sensitivity=None,
            pricing=None,
            value_chain=None,
            opex_by_category={},
            opex_category_labels={},
        )
        assert "МАРКЕР_DESCRIPTION_123" in html_str
        assert "МАРКЕР_РИСК_ABC" in html_str
        assert "МАРКЕР_ЗАДАЧА_XYZ" in html_str

    async def test_404_for_unknown_project(self, db_session: AsyncSession):
        with pytest.raises(ProjectNotFoundForExport):
            await generate_project_pdf(db_session, 999999)


# ============================================================
# Endpoint tests
# ============================================================


class TestExportPdfEndpoint:
    async def test_returns_pdf_with_correct_mime(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
    ):
        project_id, _, _, _ = await _seed_minimal_project(db_session)
        await db_session.commit()

        resp = await auth_client.get(
            f"/api/projects/{project_id}/export/pdf"
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith(PDF_MIME)
        assert resp.content[:5] == b"%PDF-"

    async def test_filename_in_content_disposition(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
    ):
        project_id, _, _, _ = await _seed_minimal_project(db_session)
        await db_session.commit()

        resp = await auth_client.get(
            f"/api/projects/{project_id}/export/pdf"
        )
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert f"project_{project_id}" in cd
        assert ".pdf" in cd

    async def test_cyrillic_project_name_in_header(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """RFC 5987 filename* для кириллицы (регрессия общего бага)."""
        from app.models import Project

        project_id, _, _, _ = await _seed_minimal_project(db_session)
        project = await db_session.get(Project, project_id)
        assert project is not None
        project.name = "Русский PDF проект"
        await db_session.flush()
        await db_session.commit()

        resp = await auth_client.get(
            f"/api/projects/{project_id}/export/pdf"
        )
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "filename*=UTF-8''" in cd
        assert "%D0" in cd

    async def test_404_for_unknown_project(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/projects/999999/export/pdf")
        assert resp.status_code == 404

    async def test_unauthorized(self, client: AsyncClient):
        resp = await client.get("/api/projects/1/export/pdf")
        assert resp.status_code == 401


# ============================================================
# C #27: Section-selection tests
# ============================================================


class TestPdfSectionSelection:
    """C #27: GET ?sections=... query param behaviour."""

    async def test_pdf_export_all_sections_default(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """C #27: GET без sections param — все 17 секций, валидный PDF."""
        project_id, _, _, _ = await _seed_minimal_project(db_session)
        await db_session.commit()

        resp = await auth_client.get(f"/api/projects/{project_id}/export/pdf")
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("application/pdf")
        assert len(resp.content) > 1000
        assert resp.content[:5] == b"%PDF-"
        # Без sections — filename НЕ содержит _partial
        cd = resp.headers.get("content-disposition", "")
        assert "_partial" not in cd

    async def test_pdf_export_subset_sections(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """C #27: sections=kpi,pnl → меньший PDF, _partial в filename."""
        project_id, _, _, _ = await _seed_minimal_project(db_session)
        await db_session.commit()

        resp = await auth_client.get(
            f"/api/projects/{project_id}/export/pdf?sections=kpi,pnl"
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.content) > 0
        assert resp.content[:5] == b"%PDF-"
        cd = resp.headers.get("content-disposition", "")
        assert "_partial.pdf" in cd

    async def test_pdf_export_empty_sections_422(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """C #27: ?sections= (пустая строка) → 422."""
        project_id, _, _, _ = await _seed_minimal_project(db_session)
        await db_session.commit()

        resp = await auth_client.get(
            f"/api/projects/{project_id}/export/pdf?sections="
        )
        assert resp.status_code == 422

    async def test_pdf_export_invalid_section_422(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """C #27: ?sections=xyz,kpi → 422 с указанием невалидного ID."""
        project_id, _, _, _ = await _seed_minimal_project(db_session)
        await db_session.commit()

        resp = await auth_client.get(
            f"/api/projects/{project_id}/export/pdf?sections=xyz,kpi"
        )
        assert resp.status_code == 422
        assert "xyz" in resp.text
