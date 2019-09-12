
# Extract axial and equitorial components of a octahedral complex
#  @param mol The mol3D object for the complex
#  @param liglist List of ligands
#  @return ligdents List of ligand dents
#  @return ligcons List of ligand connection indices (in mol)
def ligand_breakdown(mol, flag_loose=False, BondedOct=False):
    # this function takes an octahedral
    # complex and returns ligands
    metal_index = mol.findMetal()[0]
    bondedatoms = mol.getBondedAtomsSmart(metal_index, oct=True)
    # print('!!!!!boundatoms', bondedatoms)
    #	print('from get oct' + str(bondedatoms))
    #	print('***\n')
    bonded_atom_symbols = [mol.getAtom(i).symbol() for i in bondedatoms]
    counter = 0
    liglist = []
    ligdents = []
    ligcons = []
    for atom in bondedatoms:
        # print('this atom type is ' + mol.getAtom(atom).symbol())
        # print('conection number ' + str(atom) + " of " + str(bondedatoms))
        fragment = mol.findsubMol(atom, metal_index)
        this_cons = [x for x in fragment if (x in bondedatoms)]
        # print('fragment',fragment)
        # print('this_cons',this_cons)
        unique = True
        for i, unique_ligands in enumerate(liglist):
            if sorted(fragment) == sorted(unique_ligands):
                unique = False
                matched = i
        if unique:
            liglist.append(fragment)
            ligdents.append(1)
            ligcons.append(this_cons)
        else:
            ligdents[matched] += 1
    return liglist, ligdents, ligcons


def ligand_assign(mol, liglist, ligdents, ligcons, loud=False, name=False):
    valid = True
    loud = False
    pentadentate = False
    metal_index = mol.findMetal()[0]
    built_ligand_list = list()
    lig_natoms_list = list()
    unique_ligands = list()
    ligand_counts = list()
    all_ligand_counts = [0, 0, 0, 0, 0, 0]
    ligand_records = list()
    ax_con_int_list = list()
    eq_con_int_list = list()
    ax_natoms_list = list()
    eq_natoms_list = list()
    n_ligs = len(liglist)
    max_dent = max(ligdents)
    min_dent = min(ligdents)
    if loud:
        print('********************************************')
        print(("n_ligs = " + str(n_ligs)))
        print(("max d = " + str(max_dent)))
        print(("min_dent = " + str(min_dent)))
        print(("ligand list is" + str(liglist)))
        print(('denticities are  ' + str(ligdents)))
    if (max(ligdents) == 4) and (min(ligdents) != 1):
        valid = False
        print(('bad denticities: ' + str(ligdents)))
        print(('min denticities: ' + str(min(ligdents))))
    if max(ligdents) > 4:
        #### Handling of pentadentate ligands goes here. #####
        if max(ligdents) == 5 and min(ligdents) == 1:
            pentadentate = True
        else:
            valid = False
            print('bad denticities: ' + str(ligdents))
            print('max denticities: ' + str(min(ligdents)))
    if n_ligs > 3 and min(ligdents) > 1:
        valid = False
        print(('too many ligs ' + str((n_ligs))))
    eq_lig_list = list()
    ax_lig_list = list()
    ax_con_list = list()
    eq_con_list = list()
    for i, ligand_indices in enumerate(liglist):
        this_ligand = ligand(mol, ligand_indices, ligdents[i])
        this_ligand.obtain_mol3d()
        built_ligand_list.append(this_ligand)
        lig_natoms_list.append(this_ligand.mol.natoms)
    for j, built_ligs in enumerate(built_ligand_list):
        # test if ligand is unique
        sl = [atom.symbol() for atom in built_ligs.mol.getAtoms()]
        if loud:
            print(('checking lig ' + str(j) + ' : ' + str(sl)))
        unique = 1
        for i, other_sl in enumerate(unique_ligands):
            if sorted(sl) == sorted(other_sl):
                # duplicate
                unique = 0
                ligand_counts[i] += 1
        if unique == 1:
            unique_ligands.append(sl)
            ligand_counts.append(1)
            ligand_records.append(j)
    # loop to bin ligands:
    for j, built_ligs in enumerate(built_ligand_list):
        # test if ligand is unique
        sl = [atom.symbol() for atom in built_ligs.mol.getAtoms()]
        unique = 1
        for i, other_sl in enumerate(unique_ligands):
            if sorted(sl) == sorted(other_sl):
                # duplicate
                # print(i,ligand_counts[i])
                all_ligand_counts[j] = ligand_counts[i]

    if loud:
        print(('unique ligands' + str(unique_ligands)))
        print(('ligand counts' + str(ligand_counts)))
        print(('ligand records ' + str(ligand_records)))
        print((str(max(ligand_counts)) +
               ' is the max and min in  ' + str(min(ligand_counts))))
    n_unique_ligs = len(unique_ligands)
    if (n_ligs == 3) or (n_ligs == 4):  # most common case,
        # one/two equitorial and 2 axial mono
        # or three bidentate
        for i, ligs in enumerate(liglist):
            if ligdents[i] == 1 and min_dent == 1:  # anything with equitorial monos will
                # have higher than 4 n_ligs
                ax_lig_list.append(i)
                if loud:
                    print(('choosing ' + str(i) + ' as ax based on dent =1'))
                ax_con_list.append(ligcons[i])
            if (ligdents[i] >= 2) and (min_dent == 1):
                eq_lig_list.append(i)
                if loud:
                    print(('choosing lig ' + str(i) + ' as eq based on high dent'))
                eq_con_list.append(ligcons[i])
        if (n_ligs == 3) and (min_dent == max_dent):
            if n_unique_ligs == 1:
                # take any 2, they are all the same
                if loud:
                    print('triple bidentate case')
                ax_lig_list.append(0)
                eq_lig_list.append(1)
                eq_lig_list.append(2)
                ax_con_list.append(ligcons[0])
                eq_con_list.append(ligcons[1])
                eq_con_list.append(ligcons[2])
            elif min_dent == 2 and max_dent == 2 and n_ligs == 3 and not n_unique_ligs == 1:
                # this is a hetero/bidentate case
                for i, ligs in enumerate(liglist):
                    if all_ligand_counts[i] == 2:
                        eq_lig_list.append(i)
                        eq_con_list.append(ligcons[i])
                    elif all_ligand_counts[i] == 1:
                        ax_lig_list.append(i)
                        ax_con_list.append(ligcons[i])
    elif (n_ligs == 6):  # all mono  case,
        minz = 500
        maxz = -500
        if loud:
            print('monodentate case')
        allowed = list(range(0, 6))
        not_eq = list()
        for j, built_ligs in enumerate(built_ligand_list):
            this_z = sum([mol.getAtom(ii).coords()[2]
                          for ii in ligcons[j]])/len(ligcons[j])
            if this_z < minz:
                minz = this_z
                bot_lig = j
                bot_con = ligcons[j]
            if loud:
                print(('updating bot axial to ' + str(bot_lig)))
            if this_z > maxz:
                maxz = this_z
                top_lig = j
                top_con = ligcons[j]
            if loud:
                print(('updating top axial to ' + str(top_lig)))
        not_eq.append(bot_lig)
        not_eq.append(top_lig)

        allowed = [x for x in allowed if ((x not in not_eq))]
        if len(allowed) != 4:
            print(('error in decomp of monodentate case!', allowed))
        eq_lig_list = allowed
        eq_con_list = [ligcons[i] for i in allowed]
        ax_lig_list = [top_lig, bot_lig]
        ax_con_list = [top_con, bot_con]
        if loud:
            print(('geometric eq_list ' + str(eq_lig_list)))
            print(('geometric ax_list ' + str(eq_lig_list)))
        if (max(ligand_counts) != 4) or (min(ligand_counts) != 2):
            if loud:
                print('not a 4-6 case')
            if (max(ligand_counts) == 6):
                if loud:
                    print('6-homoleptic, using geo values')
            # ax=ligand_records[ligand_counts.index(6)]
            # eq_lig=ligand_records[ligand_counts.index(6)]
            else:
                if loud:
                    print('monodentates not the same, using geo values ')
                    print(ligand_counts)
                    print(unique_ligands)
        elif n_unique_ligs == 2:
            if loud:
                print('this is a  4-6 case')
            allowed = list(range(0, 6))
            ax_lig_list = [i for i in allowed if (all_ligand_counts[i] == 2)]
            eq_lig_list = [i for i in allowed if (all_ligand_counts[i] == 4)]
            ax_con_list = [ligcons[i] for i in ax_lig_list]
            eq_con_list = [ligcons[i] for i in eq_lig_list]
    elif n_ligs == 2 and pentadentate:
        #### Handling for pentadentate scaffolds ####
        minz = 500
        maxz = -500
        if loud:
            print('pentadentate case')
        allowed = range(0, 1)
        not_eq = list()
        for j, built_ligs in enumerate(built_ligand_list):
            if len(ligcons[j]) == 1:
                #### This is the axial ligand ####
                # print(j, 'axial lig')
                z_coord = [mol.getAtom(ii).coords()[2] for ii in ligcons[j]][0]
                if z_coord < 0:
                    bot_lig = j
                    bot_con = ligcons[j]
                    not_eq.append(bot_lig)
                else:
                    top_lig = j
                    top_con = ligcons[j]
                    not_eq.append(top_lig)
            else:
                pentadentate_z_list = [mol.getAtom(
                    ii).coords()[2] for ii in ligcons[j]]
                if loud:
                    print('pentadentate Z LIST!')
                    print(pentadentate_z_list)
                for k, z_val in enumerate(pentadentate_z_list):
                    if z_val > maxz:
                        maxz = z_val
                        top_lig = j
                        top_con = [ligcons[j][k]]
                    if z_val < minz:
                        minz = z_val
                        bot_lig = j
                        bot_con = [ligcons[j][k]]
        allowed = [x for x in allowed if ((x not in not_eq))]
        eq_lig_list = allowed
        eq_con_list = [
            list(set([ligcons[i] for i in allowed][0])-set(top_con)-set(bot_con))]
        ax_lig_list = [top_lig, bot_lig]
        ax_con_list = [top_con, bot_con]
        if loud:
            print('con lists', eq_con_list, ax_con_list)
        ###########################################################################################
        # In the above, the pentadentate ligand is classified as both axial and equatorial.       #
        # The lc atoms are decided by the z-position. Thus the pentadentate ligand has 4 eq-lc    #
        # and 1 ax-lc. Currently should be able to check this and set that up.                    #
        ###########################################################################################
    ############### DONE WITH CLASSIFICATION ######
    # ax_lig=ligand_records[ligand_counts.index(2)]
    # eq_lig=ligand_records[ligand_counts.index(4)]
    ax_ligand_list = [built_ligand_list[i] for i in ax_lig_list]
    eq_ligand_list = [built_ligand_list[i] for i in eq_lig_list]
    if loud and valid:
        print(('lig_nat_list', lig_natoms_list))
        print(('eq_liq is ind ', eq_lig_list))
        print(('ax_liq is ind ', ax_lig_list))
        print(('ax built lig [0] ext ind :' +
               str(list(built_ligand_list[ax_lig_list[0]].ext_int_dict.keys()))))
        if len(ax_lig_list) > 1:
            print(('ax built lig [1] ext ind :' +
                   str(list(built_ligand_list[ax_lig_list[1]].ext_int_dict.keys()))))
        print(('eq built lig [0] ext ind: ' +
               str(list(built_ligand_list[eq_lig_list[0]].ext_int_dict.keys()))))
        print(('eq_con is ' + str((eq_con_list))))
        print(('ax_con is ' + str((ax_con_list))))
    if name:
        for i, ax_ligand in enumerate(ax_ligand_list):
            if not os.path.isdir('ligands'):
                os.mkdir('ligands')
            ax_ligand.mol.writexyz('ligands/' + name +
                                   '_' + str(i) + '_ax.xyz')
        for i, eq_ligand in enumerate(eq_ligand_list):
            if not os.path.isdir('ligands'):
                os.mkdir('ligands')
            eq_ligand.mol.writexyz('ligands/' + name +
                                   '_' + str(i) + '_eq.xyz')
    for j, ax_con in enumerate(ax_con_list):
        ax_con_int_list.append(
            [built_ligand_list[ax_lig_list[j]].ext_int_dict[i] for i in ax_con])  # convert to interal index
    for j, eq_con in enumerate(eq_con_list):
        eq_con_int_list.append(
            [built_ligand_list[eq_lig_list[j]].ext_int_dict[i] for i in eq_con])  # convert to interal index
    if loud:
        print(('int eq ' + str(eq_con_int_list)))
        print(('ext eq ' + str(eq_con_list)))
        print('**********************************************')
    for ax_lig in ax_lig_list:
        ax_natoms_list.append(lig_natoms_list[ax_lig])
    for eq_lig in eq_lig_list:
        eq_natoms_list.append(lig_natoms_list[eq_lig])
    return ax_ligand_list, eq_ligand_list, ax_natoms_list, eq_natoms_list, ax_con_int_list, eq_con_int_list, ax_con_list, eq_con_list, built_ligand_list
