import asyncio
import collections
import re

import discord
from discord.ext import commands
from rapidfuzz import fuzz
from rapidfuzz import process

import common.utils as utils
import common.cards as cards


class FuzzyConverter(commands.IDConverter):
    """General class for fuzzy matching. Contains functions
    needed to fuzzy convert."""

    def embed_gen(self, ctx, description):
        selection_embed = discord.Embed(
            colour=discord.Colour(0x4378FC), description="\n".join(description)
        )
        selection_embed.set_author(
            name=f"{ctx.guild.me.name}",
            icon_url=f"{str(ctx.guild.me.avatar_url_as(format=None,static_format='png', size=128))}",
        )

        return selection_embed

    def norm_embed_gen(self, ctx, list_str):
        description = collections.deque()
        description.append(
            "Multiple entries found. Please choose one of the following, or type cancel."
        )

        for n in range(len(list_str)):
            description.append(f"{n+1} - `{list_str[n]}`")

        return self.embed_gen(ctx, description)

    def unsure_embed_gen(self, ctx, item):
        description = collections.deque()
        description.append(f"Did you mean `{str(item)}`?.")
        description.append(f"Reply with yes or no.")

        return self.embed_gen(ctx, description)

    async def extract_from_list(
        self, ctx, argument, list_of_items, processors, unsure=False
    ):
        """Uses multiple scorers and processors for a good mix of accuracy and fuzzy-ness"""
        combined_list = []

        scorers = (fuzz.token_set_ratio, fuzz.WRatio)

        for scorer in scorers:
            for processor in processors:
                fuzzy_list = process.extract(
                    argument,
                    list_of_items,
                    processor=processor,
                    scorer=scorer,
                    score_cutoff=80,
                    limit=5,
                )
                if fuzzy_list:
                    combined_entries = [e[0] for e in combined_list]

                    if (
                        processor == fuzz.WRatio
                    ):  # WRatio isn't the best, so we add in extra filters to make sure everythings turns out ok
                        new_members = [
                            e
                            for e in fuzzy_list
                            if e[0] not in combined_entries
                            and (len(processor(e[0])) >= 2 or len(argument) <= 2)
                            and argument.lower() in processor(e[0])
                        ]

                    else:
                        new_members = [
                            e
                            for e in fuzzy_list
                            if e[0] not in combined_entries
                            and argument.lower() in processor(e[0])
                        ]

                    combined_list.extend(new_members)

                    if len(combined_list) > 1:
                        if len(combined_list) > 5:
                            combined_list = combined_list[:5]
                        return await self.selection_handler(ctx, combined_list)

        if combined_list == []:
            return

        if len(combined_list) != 1:
            return await self.selection_handler(ctx, combined_list)
        if unsure and combined_list[0][1] < 95:  # entries score
            await self.unsure_select_handler(ctx, combined_list[0][0])
        return combined_list[0][0]  # actual entry itself

    async def unsure_select_handler(self, ctx, item):
        selection_embed = self.unsure_embed_gen(ctx, item)
        await ctx.reply(embed=selection_embed)

        def check(m):
            return m.channel == ctx.channel and m.author == ctx.author

        try:
            msg = await ctx.bot.wait_for("message", timeout=15.0, check=check)
        except asyncio.TimeoutError:
            raise commands.BadArgument("No option selected. Canceling command.")

        else:
            lowered = msg.content.lower()

            # yes, this snippet is copied from the source of d.py, but it's slightly edited so...
            if lowered in ("yes", "y", "true", "t", "1"):
                return
            elif lowered in ("no", "n", "false", "f", "0"):
                raise utils.CustomCheckFailure(
                    "Couldn't verify the entry. Canceled command."
                )
            else:
                raise commands.BadArgument("Invalid input. Canceled command.")

    async def selection_handler(self, ctx, options):
        entries = [o[0] for o in options]
        selection_embed = self.norm_embed_gen(ctx, entries)
        await ctx.reply(embed=selection_embed)

        def check(m):
            return m.channel == ctx.channel and m.author == ctx.author

        try:
            msg = await ctx.bot.wait_for("message", timeout=15.0, check=check)
        except asyncio.TimeoutError:
            raise commands.BadArgument("No entry selected. Canceling command.")

        else:
            if msg.content.lower() == "cancel":
                raise utils.CustomCheckFailure("Canceled command.")
            elif not msg.content.isdigit():
                raise commands.BadArgument("Invalid input. Canceled command.")
            else:
                selection = int(msg.content)
                if selection > len(entries):
                    raise commands.BadArgument("Invalid number. Canceled command.")
                else:
                    return entries[selection - 1]


class FuzzyMemberConverter(FuzzyConverter):
    """Uses fuzzy matching to match strings to a member.
    Most of this initial code is very similar code to MemberConverter
    Checks for ID then mention, username with discrim, then...
    fuzzy searches via nicks first, then usernames"""

    def norm_embed_gen(self, ctx, entries):
        list_str = [f"`{m.display_name} ({str(m)})`" for m in entries]

        description = collections.deque()
        description.append(
            "Multiple entries found. Please choose one of the following, or type cancel."
        )

        for n in range(len(list_str)):
            description.append(f"{n+1} - {list_str[n]}")

        return self.embed_gen(ctx, description)

    def get_display_name(self, member):
        """For some reason fuzzywuzzy runs the processor on the query,
        so we use a quick isinstance to make sure everything goes ok
        without losing too much performance as a try error would do."""

        if isinstance(member, discord.Member):
            return member.display_name.lower()
        else:
            return member

    def get_name(self, member):
        """Same thing as above, but with a normal name."""
        if isinstance(member, discord.Member):
            return member.name.lower()
        else:
            return member

    async def convert(self, ctx, argument):
        result = None
        match = self._get_id_match(argument) or re.match(r"<@!?([0-9]+)>$", argument)

        if match != None:
            user_id = int(match.group(1))
            result = ctx.guild.get_member(user_id) or discord.utils.get(
                ctx.message.mentions, id=user_id
            )
        elif "#" in argument:
            hash_split = argument.split("#")
            result = discord.utils.get(
                ctx.guild.members, name=hash_split[0], discriminator=hash_split[1]
            )

        if result == None:
            result = await self.extract_from_list(
                ctx, argument, ctx.guild.members, (self.get_display_name, self.get_name)
            )

        if result is None:
            raise commands.BadArgument(f'Member "{argument}" not found.')
        return result


class FuzzyOCNameConverter(FuzzyConverter):
    """Uses fuzzy matching to match strings to an OC.
    Returns a Discord object representing the user.
    Does not handle the hosts."""

    def get_name(self, card):
        """See FuzzyMemberConverter's get_display_name."""
        if isinstance(card, cards.Card):
            return card.oc_name
        else:
            return card

    async def convert(self, ctx, argument) -> discord.Object:
        result = None
        result = await self.extract_from_list(
            ctx, argument, cards.participants, [self.get_name]
        )

        if result is None:
            raise commands.BadArgument(f'Role "{argument}" not found.')
        return discord.Object(result.user_id)
