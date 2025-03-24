"""Base agent loop implementation."""

import logging
import asyncio
from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from datetime import datetime

from computer import Computer
from .experiment import ExperimentManager

logger = logging.getLogger(__name__)


class AgentLoop(Enum):
    """Enumeration of available loop types."""

    ANTHROPIC = auto()  # Anthropic implementation
    OMNI = auto()  # OmniLoop implementation
    # Add more loop types as needed


class BaseLoop(ABC):
    """Base class for agent loops that handle message processing and tool execution."""

    ###########################################
    # INITIALIZATION AND CONFIGURATION
    ###########################################

    def __init__(
        self,
        computer: Computer,
        model: str,
        api_key: str,
        max_tokens: int = 4096,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        base_dir: Optional[str] = "trajectories",
        save_trajectory: bool = True,
        only_n_most_recent_images: Optional[int] = 2,
        **kwargs,
    ):
        """Initialize base agent loop.

        Args:
            computer: Computer instance to control
            model: Model name to use
            api_key: API key for provider
            max_tokens: Maximum tokens to generate
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds
            base_dir: Base directory for saving experiment data
            save_trajectory: Whether to save trajectory data
            only_n_most_recent_images: Maximum number of recent screenshots to include in API requests
            **kwargs: Additional provider-specific arguments
        """
        self.computer = computer
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.base_dir = base_dir
        self.save_trajectory = save_trajectory
        self.only_n_most_recent_images = only_n_most_recent_images
        self._kwargs = kwargs
        self.message_history = []
        # self.tool_manager = BaseToolManager(computer)

        # Initialize experiment manager
        if self.save_trajectory and self.base_dir:
            self.experiment_manager = ExperimentManager(
                base_dir=self.base_dir,
                only_n_most_recent_images=only_n_most_recent_images,
            )
            # Track directories for convenience
            self.run_dir = self.experiment_manager.run_dir
            self.current_turn_dir = self.experiment_manager.current_turn_dir
        else:
            self.experiment_manager = None
            self.run_dir = None
            self.current_turn_dir = None

        # Initialize basic tracking
        self.turn_count = 0

    async def initialize(self) -> None:
        """Initialize both the API client and computer interface with retries."""
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    f"Starting initialization (attempt {attempt + 1}/{self.max_retries})..."
                )

                # Initialize API client
                await self.initialize_client()

                logger.info("Initialization complete.")
                return
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Initialization failed (attempt {attempt + 1}/{self.max_retries}): {str(e)}. Retrying..."
                    )
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(
                        f"Initialization failed after {self.max_retries} attempts: {str(e)}"
                    )
                    raise RuntimeError(f"Failed to initialize: {str(e)}")

        ###########################################

    # ABSTRACT METHODS TO BE IMPLEMENTED BY SUBCLASSES
    ###########################################

    @abstractmethod
    async def initialize_client(self) -> None:
        """Initialize the API client and any provider-specific components.

        This method must be implemented by subclasses to set up
        provider-specific clients and tools.
        """
        raise NotImplementedError

    @abstractmethod
    async def run(self, messages: List[Dict[str, Any]]) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the agent loop with provided messages.

        This method handles the main agent loop including message processing,
        API calls, response handling, and action execution.

        Args:
            messages: List of message objects

        Yields:
            Dict containing response data
        """
        raise NotImplementedError

    ###########################################
    # EXPERIMENT AND TRAJECTORY MANAGEMENT
    ###########################################

    def _setup_experiment_dirs(self) -> None:
        """Setup the experiment directory structure."""
        if self.experiment_manager:
            # Use the experiment manager to set up directories
            self.experiment_manager.setup_experiment_dirs()

            # Update local tracking variables
            self.run_dir = self.experiment_manager.run_dir
            self.current_turn_dir = self.experiment_manager.current_turn_dir

    def _create_turn_dir(self) -> None:
        """Create a new directory for the current turn."""
        if self.experiment_manager:
            # Use the experiment manager to create the turn directory
            self.experiment_manager.create_turn_dir()

            # Update local tracking variables
            self.current_turn_dir = self.experiment_manager.current_turn_dir
            self.turn_count = self.experiment_manager.turn_count

    def _log_api_call(
        self, call_type: str, request: Any, response: Any = None, error: Optional[Exception] = None
    ) -> None:
        """Log API call details to file.

        Preserves provider-specific formats for requests and responses to ensure
        accurate logging for debugging and analysis purposes.

        Args:
            call_type: Type of API call (e.g., 'request', 'response', 'error')
            request: The API request data in provider-specific format
            response: Optional API response data in provider-specific format
            error: Optional error information
        """
        if self.experiment_manager:
            # Use the experiment manager to log the API call
            provider = getattr(self, "provider", "unknown")
            provider_str = str(provider) if provider else "unknown"

            self.experiment_manager.log_api_call(
                call_type=call_type,
                request=request,
                provider=provider_str,
                model=self.model,
                response=response,
                error=error,
            )

    def _save_screenshot(self, img_base64: str, action_type: str = "") -> None:
        """Save a screenshot to the experiment directory.

        Args:
            img_base64: Base64 encoded screenshot
            action_type: Type of action that triggered the screenshot
        """
        if self.experiment_manager:
            self.experiment_manager.save_screenshot(img_base64, action_type)
