import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel
from app.config import settings

logger = logging.getLogger("filingguard.extraction.arelle_runner")


class ArelleRunResult(BaseModel):
    success: bool
    file_path: str
    error_message: Optional[str] = None
    warnings: List[str] = []
    facts_count: int = 0
    contexts_count: int = 0
    units_count: int = 0


class ArelleRunner:
    """
    Isolated runner for processing Inline XBRL and XBRL filings via Arelle.
    Configures sandboxed XDG cache directory to protect host OS permissions.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or (settings.DATA_DIR / "cache" / "arelle")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Ensure Arelle uses our dedicated cache directory
        os.environ["XDG_CONFIG_HOME"] = str(self.cache_dir.resolve())
        os.environ["XDG_CACHE_HOME"] = str(self.cache_dir.resolve())

    def parse_filing(self, file_path: str) -> Tuple[ArelleRunResult, Any]:
        """
        Loads an Inline XBRL or XBRL document with Arelle's Cntlr and ModelManager.
        Returns (ArelleRunResult, modelXbrl).
        If loading fails, captures error and returns non-crashing result.
        """
        path_obj = Path(file_path)
        if not path_obj.exists():
            return ArelleRunResult(
                success=False,
                file_path=file_path,
                error_message=f"File not found: {file_path}",
            ), None

        from arelle import Cntlr, FileSource, ModelXbrl

        cntlr: Optional[Cntlr.Cntlr] = None
        model_xbrl = None
        try:
            cntlr = Cntlr.Cntlr(logFileName=None, disable_persistent_config=True)
            cntlr.modelManager.loadCustomTransforms = False

            # Load model from file path
            file_source = FileSource.openFileSource(str(path_obj.resolve()), cntlr)
            model_xbrl = cntlr.modelManager.load(file_source)

            if model_xbrl is None or not hasattr(model_xbrl, "facts"):
                if file_source and hasattr(file_source, "close"):
                    file_source.close()
                if cntlr and hasattr(cntlr, "close"):
                    cntlr.close()
                return ArelleRunResult(
                    success=False,
                    file_path=file_path,
                    error_message="Arelle returned null or empty ModelXbrl",
                ), None

            # Attach resources to model_xbrl for reliable closing
            model_xbrl._file_source = file_source
            model_xbrl._cntlr = cntlr

            facts_cnt = len(model_xbrl.facts)
            contexts_cnt = len(model_xbrl.contexts)
            units_cnt = len(model_xbrl.units)

            result = ArelleRunResult(
                success=True,
                file_path=file_path,
                facts_count=facts_cnt,
                contexts_count=contexts_cnt,
                units_count=units_cnt,
            )
            return result, model_xbrl

        except Exception as e:
            logger.error(f"Arelle execution error processing {file_path}: {e}")
            if model_xbrl is not None and hasattr(model_xbrl, "close"):
                try:
                    model_xbrl.close()
                except Exception:
                    pass
            if cntlr is not None and hasattr(cntlr, "close"):
                try:
                    cntlr.close()
                except Exception:
                    pass
            return ArelleRunResult(
                success=False,
                file_path=file_path,
                error_message=str(e),
            ), None

    def close_model(self, model_xbrl: Any) -> None:
        """Safely close ModelXbrl, associated FileSource, and Cntlr."""
        if model_xbrl is None:
            return
        try:
            if hasattr(model_xbrl, "close"):
                model_xbrl.close()
        except Exception as e:
            logger.debug(f"Error closing model_xbrl: {e}")
        try:
            file_source = getattr(model_xbrl, "_file_source", None)
            if file_source and hasattr(file_source, "close"):
                file_source.close()
        except Exception as e:
            logger.debug(f"Error closing file_source: {e}")
        try:
            cntlr = getattr(model_xbrl, "_cntlr", None)
            if cntlr and hasattr(cntlr, "close"):
                cntlr.close()
        except Exception as e:
            logger.debug(f"Error closing cntlr: {e}")
