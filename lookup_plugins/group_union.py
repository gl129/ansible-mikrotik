
from ansible.plugins.lookup import LookupBase
from ansible.errors import AnsibleError

class LookupModule(LookupBase):

    def run(self, terms, variables=None, **kwargs):
        """
        Union all variables like <prefix>_<group>
        for all groups names to which the host belongs
        Example:
        if host belongs to groups "rb760", "filial" and "outer"
        lookup( "group_union", "ethernets" )
        will result union all defined variables like
        ethernets_rb760, ethernets_filial, ethernets_outer
        """
        if variables is not None:
            self._templar.available_variables = variables
        myvars = getattr( self._templar, '_available_variables', {} )

        ret = []

        prefix = terms[0] if len(terms) == 1 else None
        if not isinstance(prefix,str):
            raise AnsibleError( f'Invalid variable prefix, "{terms}" is not a string' )

        for group in myvars['group_names']:
            var = f'{prefix}_{group}'
            if var in myvars:
                value = self._templar.template( myvars[var], fail_on_undefined=True )
                ret += value

        return [ ret ]
