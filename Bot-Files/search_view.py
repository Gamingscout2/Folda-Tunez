"""Interactive search-result picker."""
import discord
from discord.ui import View, Button


class SearchView(View):
    def __init__(self, entries, ctx):
        super().__init__(timeout=30)
        self.entries = entries
        self.ctx = ctx
        self.selected_entry = None
        self.message = None
        for idx in range(min(5, len(entries))):
            btn = Button(style=discord.ButtonStyle.primary, label=str(idx + 1))
            btn.callback = self._make_cb(idx)
            self.add_item(btn)
        cancel = Button(style=discord.ButtonStyle.danger, label="Cancel")
        cancel.callback = self._cancel_cb
        self.add_item(cancel)

    def _make_cb(self, idx):
        async def cb(interaction: discord.Interaction):
            if interaction.user != self.ctx.author:
                await interaction.response.send_message(
                    "You didn't start this search!", ephemeral=True
                )
                return
            self.selected_entry = self.entries[idx]
            await interaction.response.defer()
            self.stop()
        return cb

    async def _cancel_cb(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "You didn't start this search!", ephemeral=True
            )
            return
        self.selected_entry = None
        await interaction.response.defer()
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass